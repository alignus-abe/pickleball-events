import warnings
import argparse
from inference import get_model
import supervision as sv
import cv2
import requests
import datetime
from pathlib import Path
import time
import json
from datetime import timedelta
import os
from typing import Dict, Any
from utils.sound import play_sound

warnings.filterwarnings('ignore', message='Specified provider.*')
os.environ['QT_QPA_PLATFORM'] = 'xcb'

def get_video_source(source):
    if source.isdigit():
        return int(source)
    return source

def create_control_file():
    control_file = Path("/tmp/pickleball_control.json")
    if not control_file.exists():
        with open(control_file, "w") as f:
            json.dump({"active": True, "last_ball_detection": None}, f)
    return control_file

def update_control_state(control_file, active=None, last_detection=None):
    with open(control_file, "r") as f:
        state = json.load(f)
    
    if active is not None:
        state["active"] = active
    if last_detection is not None:
        state["last_ball_detection"] = last_detection
    
    with open(control_file, "w") as f:
        json.dump(state, f)

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")
            
        with open(config_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in config file: {config_path}")

def main(video_source: str, recording_path: str = None):
    config = load_config()
    model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])

    video_source = get_video_source(video_source)
    cap = cv2.VideoCapture(video_source)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    if not cap.isOpened():
        print(f"Error: Could not open video source {video_source}")
        return

    RECT_LEFT = config['rectangle']['left']
    RECT_RIGHT = config['rectangle']['right']
    RECT_TOP = config['rectangle']['top']
    RECT_BOTTOM = config['rectangle']['bottom']

    prev_ball_x = None
    crossed_left_to_right = False
    crossed_right_to_left = False

    bounding_box_annotator = sv.BoundingBoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    # Add recording variables
    is_recording = False
    recording_start_time = None
    last_recording_end_time = None
    out = None

    control_file = create_control_file()
    last_active_check = time.time()
    last_frame_save = time.time()
    SLEEP_AFTER_MINUTES = 5  # Sleep after 5 minutes of no ball detection

    # Create static folder at start of main
    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)

    # After camera acquisition and first frame
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            play_sound("initiate")
            webhook_data = {
                "event": "status",
                "message": "Camera Acquired",
                "timestamp": str(datetime.datetime.now())
            }
            try:
                requests.post(config['webhook_url'], json=webhook_data)
            except requests.exceptions.RequestException as e:
                print(f"Failed to send webhook to {config['webhook_url']}: {e}")

    first_ball_detected = False

    while True:
        # Check control file every second
        if time.time() - last_active_check >= 1:
            with open(control_file, "r") as f:
                state = json.load(f)
            
            if not state["active"]:
                time.sleep(1)  # Sleep to reduce CPU usage
                last_active_check = time.time()
                continue
            
            # Check for auto-sleep if no ball detected
            if state["last_ball_detection"]:
                last_detection = datetime.fromisoformat(state["last_ball_detection"])
                if datetime.now() - last_detection > timedelta(minutes=SLEEP_AFTER_MINUTES):
                    update_control_state(control_file, active=False)
                    print(f"No ball detected for {SLEEP_AFTER_MINUTES} minutes, entering sleep mode")
                    continue
            
            last_active_check = time.time()

        ret, frame = cap.read()
        if not ret:
            break

        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)
        mask = detections.class_id == 2
        detections = detections[mask]

        annotated_frame = bounding_box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        cv2.rectangle(annotated_frame, (RECT_LEFT, RECT_TOP), (RECT_RIGHT, RECT_BOTTOM), (0, 0, 255), 2)

        if len(detections) > 0:
            ball_x = detections.xyxy[0][0]

            if prev_ball_x is not None:
                if prev_ball_x < RECT_LEFT < ball_x and not crossed_left_to_right:
                    webhook_data = {
                        "event": "cross",
                        "direction": "left_to_right",
                        "timestamp": str(datetime.datetime.now())
                    }
                    try:
                        requests.post(config['webhook_url'], json=webhook_data)
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to send webhook to {config['webhook_url']}: {e}")
                    crossed_left_to_right = True
                    crossed_right_to_left = False
                elif prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left:
                    webhook_data = {
                        "event": "cross",
                        "direction": "right_to_left",
                        "timestamp": str(datetime.datetime.now())
                    }
                    try:
                        requests.post(config['webhook_url'], json=webhook_data)
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to send webhook to {config['webhook_url']}: {e}")
                    crossed_right_to_left = True
                    crossed_left_to_right = False

            prev_ball_x = ball_x

            if not first_ball_detected:
                play_sound("activated")
                webhook_data = {
                    "event": "status",
                    "message": "ball detected",
                    "timestamp": str(datetime.datetime.now())
                }
                try:
                    requests.post(config['webhook_url'], json=webhook_data)
                except requests.exceptions.RequestException as e:
                    print(f"Failed to send webhook to {config['webhook_url']}: {e}")
                first_ball_detected = True

        if recording_path and out is None and (
            (prev_ball_x < RECT_LEFT < ball_x and not crossed_left_to_right) or 
            (prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left)
        ):
            current_time = time.time()
            
            # Check if 30 minutes have passed since last recording
            if last_recording_end_time is None or (current_time - last_recording_end_time) >= 1800:  # 30 minutes
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = str(Path(recording_path) / f"pickleball_{timestamp}.mp4")
                
                try:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    out = cv2.VideoWriter(output_path, fourcc, 30.0, (frame_width, frame_height))
                    recording_start_time = current_time
                    is_recording = True
                    print(f"Started recording to {output_path}")
                except Exception as e:
                    print(f"Failed to start recording: {e}")
                    out = None

        # Handle recording logic
        if is_recording and out is not None:
            out.write(annotated_frame)
            
            # Check if 10 minutes have passed
            if time.time() - recording_start_time >= 600:  # 10 minutes
                out.release()
                out = None
                is_recording = False
                last_recording_end_time = time.time()
                print("Finished recording")

        current_time = time.time()
        
        # Save frame every 3 seconds - moved after frame is processed
        if current_time - last_frame_save >= 3:
            try:
                output_path = static_dir / 'current-view.png'
                cv2.imwrite(str(output_path), annotated_frame)
                last_frame_save = current_time
            except Exception as e:
                print(f"Error saving frame: {e}")
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Shutdown handling
    play_sound("terminated")
    webhook_data = {
        "event": "status",
        "message": "Server shutting down",
        "timestamp": str(datetime.datetime.now())
    }
    try:
        requests.post(config['webhook_url'], json=webhook_data)
    except requests.exceptions.RequestException as e:
        print(f"Failed to send webhook to {config['webhook_url']}: {e}")

    # Cleanup
    if out is not None:
        out.release()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pickleball Tracking Script")
    parser.add_argument("--source", type=str, default="0", help="Video source (0 for default webcam, 1,2,etc. for other webcams, or path to video file)")
    parser.add_argument("--recording_path", type=str, help="Path to save recorded videos")
    args = parser.parse_args()

    main(args.source, args.recording_path)