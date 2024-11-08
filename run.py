import argparse
from inference import get_model
import supervision as sv
import cv2
from config import load_config
import requests
import datetime
import os
from pathlib import Path
import time

def get_video_source(source):
    if source.isdigit():
        return int(source)
    return source

def main(video_source: str, recording_path: str = None):
    config = load_config()

    model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])

    video_source = get_video_source(video_source)
    cap = cv2.VideoCapture(video_source)

    # Set camera resolution to 1920x1080
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    # Create named window with specific size
    cv2.namedWindow('Pickleball Tracking', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Pickleball Tracking', 960, 540)  # Half of 1920x1080

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

    WEBHOOK_URL = config['webhook']['url']

    # Add recording variables
    is_recording = False
    recording_start_time = None
    last_recording_end_time = None
    out = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)
        
        # Filter for ball detections only
        mask = detections.class_id == 2  # 2 is the ball class_id
        detections = detections[mask]

        annotated_frame = bounding_box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        cv2.rectangle(annotated_frame, (RECT_LEFT, RECT_TOP), (RECT_RIGHT, RECT_BOTTOM), (0, 0, 255), 2)

        if len(detections) > 0:
            ball_x = detections.xyxy[0][0]

            if prev_ball_x is not None:
                if prev_ball_x < RECT_LEFT < ball_x and not crossed_left_to_right:
                    try:
                        requests.post(WEBHOOK_URL, json={
                            "event": "cross",
                            "direction": "left_to_right",
                            "timestamp": str(datetime.datetime.now())
                        })
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to send webhook: {e}")
                    crossed_left_to_right = True
                    crossed_right_to_left = False
                elif prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left:
                    try:
                        requests.post(WEBHOOK_URL, json={
                            "event": "cross",
                            "direction": "right_to_left",
                            "timestamp": str(datetime.datetime.now())
                        })
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to send webhook: {e}")
                    crossed_right_to_left = True
                    crossed_left_to_right = False

            prev_ball_x = ball_x

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

        cv2.imshow('Pickleball Tracking', annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

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