from flask import Flask, render_template, Response, request, send_from_directory
import json
import queue
import threading
from pathlib import Path
import cv2
import datetime
from datetime import datetime, timedelta
import requests
import time
from inference import get_model
import supervision as sv
import warnings
import os
import argparse
from typing import Dict, Any

app = Flask(__name__, static_folder='static', static_url_path='/static')
event_queue = queue.Queue()

config = None
cap = None
model = None
VALID_EVENTS = {
    "SYSTEM_START": "SYSTEM STARTED",
    "CAMERA_ACQUIRED": "CAMERA ACQUIRED",
    "FIRST_BALL": "BALL DETECTED",
    "SLEEP": "PUT TO SLEEP",
    "WAKE": "WOKE UP FROM SLEEP",
    "CROSS_LTR": "BALL CROSSED LEFT TO RIGHT",
    "CROSS_RTL": "BALL CROSSED RIGHT TO LEFT",
    "SYSTEM_STOP": "SYSTEM TERMINATED"
}

recording = False
recording_thread = None
camera_sleeping = False
wake_timer = None
camera_source = 0  # Store the original camera source

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")
        
        with open(config_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in config file: {config_path}")

def send_event(event_type: str, direction: str = None):
    if event_type not in VALID_EVENTS:
        return
        
    event_data = {
        "event": "STATUS" if event_type in ["SYSTEM_START", "CAMERA_ACQUIRED", "FIRST_BALL", "SLEEP", "WAKE", "SYSTEM_STOP"] else "BALL_CROSSED",
        "message": VALID_EVENTS[event_type],
        "direction": direction,
        "timestamp": str(datetime.now())
    }

    if not direction:
        event_data.pop("direction")

    event_queue.put(event_data)
    
    if event_type in config['webhook']:
        webhook_url = config['webhook'][event_type]
    else:
        webhook_url = config['webhook']['default']

    try:
        requests.post(webhook_url, json=event_data)
    except requests.exceptions.RequestException as e:
        print(f"Failed to send webhook: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/events')
def events():
    def event_stream():
        while True:
            try:
                message = event_queue.get(timeout=1)
                yield f"data: {json.dumps(message)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    event_queue.put(data)
    return "", 200

@app.route('/current-view.png')
def serve_current_view():
    try:
        return send_from_directory(app.static_folder, 'current-view.png')
    except FileNotFoundError:
        return "Image not found", 404

@app.route('/save-current-view')
def save_current_view():
    global cap
    if not cap:
        return "Camera not initialized", 500
        
    ret, frame = cap.read()
    if not ret:
        return "Failed to capture frame", 500
        
    try:
        height, width = frame.shape[:2]
        new_width = 400
        new_height = int(height * (new_width / width))
        resized_frame = cv2.resize(frame, (new_width, new_height))
        output_path = Path(app.static_folder) / 'current-view.png'
        cv2.imwrite(str(output_path), resized_frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        return "Frame saved successfully", 200
    except Exception as e:
        return f"Error saving frame: {e}", 500

def release_camera():
    global cap
    if cap is not None:
        cap.release()
        cap = None

def initialize_camera():
    global cap, camera_source
    if cap is None:
        cap = cv2.VideoCapture(camera_source)
        if not cap.isOpened():
            raise RuntimeError("Failed to initialize camera")
        return True
    return False

def process_video():
    global cap, model, config, camera_sleeping
    
    RECT_LEFT = config['rectangle']['left']
    RECT_RIGHT = config['rectangle']['right']
    RECT_TOP = config['rectangle']['top']
    RECT_BOTTOM = config['rectangle']['bottom']

    prev_ball_x = None
    crossed_left_to_right = False
    crossed_right_to_left = False
    first_ball_detected = False

    bounding_box_annotator = sv.BoundingBoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    send_event("CAMERA_ACQUIRED")

    # Save initial frame
    ret, frame = cap.read()
    if ret:
        try:
            height, width = frame.shape[:2]
            new_width = 400
            new_height = int(height * (new_width / width))
            resized_frame = cv2.resize(frame, (new_width, new_height))
            
            output_path = Path(app.static_folder) / 'current-view.png'
            cv2.imwrite(str(output_path), resized_frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        except Exception as e:
            print(f"Error saving initial frame: {e}")

    while True:
        if camera_sleeping:
            time.sleep(0.5)  # Light sleep while checking sleep state
            continue
            
        if cap is None:
            try:
                initialize_camera()
            except RuntimeError as e:
                print(f"Failed to initialize camera: {e}")
                time.sleep(1)
                continue
                
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame")
            release_camera()
            time.sleep(1)
            continue

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
                    send_event("CROSS_LTR", "LEFT TO RIGHT")
                    crossed_left_to_right = True
                    crossed_right_to_left = False

                elif prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left:
                    send_event("CROSS_RTL", "RIGHT TO LEFT")
                    crossed_right_to_left = True
                    crossed_left_to_right = False

            prev_ball_x = ball_x

            if not first_ball_detected:
                send_event("FIRST_BALL")
                first_ball_detected = True

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    send_event("SYSTEM_STOP")

    if out is not None:
        out.release()
    cap.release()
    cv2.destroyAllWindows()

def start_flask_server(port: int):
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        print(f"Failed to start server on port {port}: {e}")

def main():
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    
    global cap, model, config
    
    config = load_config()
    
    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)
    
    warnings.filterwarnings('ignore', message='Specified provider.*')
    
    model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])
    video_source = int(config['video_source']) if config['video_source'].isdigit() else config['video_source']
    cap = cv2.VideoCapture(video_source)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video source: {video_source}")
    
    server_port = config.get('server_port', 8080)    
    server_thread = threading.Thread(target=start_flask_server, args=(server_port,))
    server_thread.daemon = True
    server_thread.start()
    print(f"Started server on port {server_port}")
    send_event("SYSTEM_START")
    
    time.sleep(2)
    
    video_thread = threading.Thread(target=process_video)
    video_thread.daemon = True
    video_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down servers...")

def stop_current_recording():
    global recording, recording_thread
    if recording and recording_thread:
        recording = False
        recording_thread.join()
        recording_thread = None

def record_video(duration_minutes):
    global recording, cap
    recording = True
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    output_path = f"recordings/{timestamp}.mp4"
    
    os.makedirs("recordings", exist_ok=True)
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))
    
    end_time = datetime.now() + timedelta(minutes=duration_minutes)
    
    while recording and datetime.now() < end_time:
        ret, frame = cap.read()
        if ret:
            out.write(frame)
            
    out.release()
    recording = False
    return output_path

@app.route('/start-new-recording/<int:num_minutes>')
def start_new_recording(num_minutes):
    global recording_thread
    
    try:
        stop_current_recording()
        
        recording_thread = threading.Thread(
            target=record_video, 
            args=(num_minutes,)
        )
        recording_thread.start()
        
        # Wait briefly to ensure recording starts
        time.sleep(0.5)
        
        output_path = f"recordings/{datetime.now().strftime('%Y-%m-%d-%H%M-%S')}.mp4"
        return {"status": "success", "file_path": output_path}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/sleep-camera')
def sleep_camera():
    global camera_sleeping, wake_timer
    
    try:
        camera_sleeping = True
        if wake_timer:
            wake_timer.cancel()
            wake_timer = None
            
        release_camera()  # Actually release the camera
        send_event("SLEEP")
        return {"status": "success", "message": "Camera put to sleep"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

def wake_timeout(duration_minutes):
    global camera_sleeping
    if not any_ball_detected_recently:
        camera_sleeping = True

@app.route('/wake-camera/<int:num_minutes>', defaults={'num_minutes': 0})
@app.route('/wake-camera', defaults={'num_minutes': 0})
def wake_camera(num_minutes):
    global camera_sleeping, wake_timer
    
    try:
        camera_sleeping = False
        initialize_camera()  # Reinitialize the camera
        
        if wake_timer:
            wake_timer.cancel()
            wake_timer = None
            
        if num_minutes:
            wake_timer = threading.Timer(
                num_minutes * 60, 
                wake_timeout, 
                args=(num_minutes,)
            )
            wake_timer.start()
            
        send_event("WAKE")
        return {
            "status": "success", 
            "message": f"Camera awakened{f' for {num_minutes} minutes' if num_minutes else ' indefinitely'}"
        }, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    main()