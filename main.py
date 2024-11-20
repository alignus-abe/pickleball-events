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
        "event": "STATUS" if event_type in ["SYSTEM_START", "CAMERA_ACQUIRED", "FIRST_BALL", "SLEEP", "WAKE", "SYSTEM_STOP"] else "BALL CROSSED",
        "message": VALID_EVENTS[event_type],
        "direction": direction,
        "timestamp": str(datetime.now())
    }
    
    if not direction:
        event_data.pop("direction")
    
    event_queue.put(event_data)
    
    try:
        webhook_url = f"http://localhost:{config['webhook']['ports'][0]}/webhook"
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

def process_video():
    global cap, model, config
    
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

    send_event("SYSTEM_START")
    send_event("CAMERA_ACQUIRED")

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

def main(video_source="0"):
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    
    global cap, model, config
    
    config = load_config()
    
    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)
    
    warnings.filterwarnings('ignore', message='Specified provider.*')
    model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])
    video_source = int(video_source) if video_source.isdigit() else video_source
    cap = cv2.VideoCapture(video_source)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video source: {video_source}")
    
    server_threads = []
    webhook_ports = config.get('webhook', {}).get('ports', [5001])
    
    for port in webhook_ports:
        server_thread = threading.Thread(target=start_flask_server, args=(port,))
        server_thread.daemon = True
        server_threads.append(server_thread)
        server_thread.start()
        print(f"Started server on port {port}")
    
    # Add a small delay to ensure servers are ready
    time.sleep(2)
    
    video_thread = threading.Thread(target=process_video)
    video_thread.daemon = True
    video_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down servers...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pickleball Vision")
    parser.add_argument("--source", type=str, default="0", 
                      help="Video source (0 for default webcam, 1,2,etc. for other webcams, or path to video file)")
    args = parser.parse_args()
    
    main(args.source)