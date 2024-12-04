from flask import Flask, render_template, Response, request, send_from_directory, jsonify
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
from collections import deque

app = Flask(__name__, static_folder='static', static_url_path='/static')
event_queue = queue.Queue()
event_list = deque(maxlen=500)
frame_queue = queue.Queue(maxsize=1000)
stop_recording_event = threading.Event()

config = None
cap = None
model = None
recording = False
recording_thread = None
camera_sleeping = False
wake_timer = None
last_ball_detection = None

VALID_EVENTS = {
    "SYSTEM_START": "SYSTEM STARTED",
    "CAMERA_ACQUIRED": "CAMERA ACQUIRED",
    "FIRST_BALL": "FIRST BALL DETECTED",
    "SLEEP": "PUT TO SLEEP",
    "WAKE": "WOKE UP FROM SLEEP",
    "CROSS_LTR": "BALL CROSSED LEFT TO RIGHT",
    "CROSS_RTL": "BALL CROSSED RIGHT TO LEFT",
    "SYSTEM_STOP": "SYSTEM STOPPED",
    "CURRENT_VIEW_SAVED": "SAVED CURRENT VIEW",
    "RECORDING_STARTED": "RECORDING STARTED",
    "RECORDING_COMPLETED": "RECORDING COMPLETED",
    "RECORDING_STOPPED": "RECORDING STOPPED"
}

# Global lock for camera access
cap_lock = threading.Lock()

@app.route('/')
def index():
    events = list(event_list)
    return render_template('index.html', initial_events=events)

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

@app.route('/get-events', methods=['GET'])
def get_events():
    return jsonify(list(event_list)), 200

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
        
    ret, frame = None, None
    with cap_lock:
        ret, frame = cap.read()
    if not ret:
        return "Failed to capture frame", 500
        
    try:
        # Resize frame first
        new_width = 400
        height, width = frame.shape[:2]
        new_height = int(height * (new_width / width))
        resized_frame = cv2.resize(frame, (new_width, new_height))
        
        # Dynamically calculate rectangle position based on resized frame
        rect_width = 40
        rect_height = 230
        rect_left = (new_width - rect_width) // 2
        rect_top = (new_height - rect_height) // 2
        rect_right = rect_left + rect_width
        rect_bottom = rect_top + rect_height

        # Annotate resized frame for display
        annotated_frame = resized_frame.copy()
        cv2.rectangle(annotated_frame, (rect_left, rect_top), (rect_right, rect_bottom), (0, 0, 255), 2)
        
        # Add bounding boxes if detection exists
        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)
        mask = detections.class_id == 2
        detections = detections[mask]
        label_annotator = sv.LabelAnnotator()
        bounding_box_annotator = sv.BoundingBoxAnnotator()
        annotated_frame = bounding_box_annotator.annotate(scene=annotated_frame, detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        # Save the annotated and resized frame
        output_path = Path(app.static_folder) / 'current-view.png'
        cv2.imwrite(str(output_path), annotated_frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        send_event("CURRENT_VIEW_SAVED")
        return "Frame saved successfully", 200
    except Exception as e:
        return f"Error saving frame: {e}", 500

@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    recordings_dir = Path('recordings')
    try:
        return send_from_directory(recordings_dir, filename)
    except FileNotFoundError:
        return "Recording not found", 404

@app.route('/start-new-recording/<int:num_minutes>')
def start_new_recording(num_minutes):
    global recording_thread, cap, frame_queue, recording

    if num_minutes <= 0:
        return {"status": "error", "message": "Recording duration must be positive"}, 400

    if cap is None or not cap.isOpened():
        return {"status": "error", "message": "Camera not available"}, 500

    try:
        # If a recording is already in progress, stop it gracefully
        if recording and recording_thread:
            stop_recording_event.set()  # Signal the recording thread to stop
            recording_thread.join()      # Wait for the thread to finish

        # Clear the frame_queue before starting a new recording
        with frame_queue.mutex:
            frame_queue.queue.clear()

        # Reset the stop event for the new recording
        stop_recording_event.clear()

        recording = True
        recording_thread = threading.Thread(
            target=record_video, 
            args=(num_minutes,),
            daemon=True
        )
        recording_thread.start()

        # Wait briefly to ensure recording starts
        time.sleep(0.5)

        send_event("RECORDING_STARTED")
        return {"status": "success", "message": f"Recording started for {num_minutes} minutes"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/sleep-camera')
def sleep_camera():
    global camera_sleeping, wake_timer

    if camera_sleeping:
        return {"status": "error", "message": "Camera is already asleep"}, 400

    try:
        camera_sleeping = True
        if wake_timer:
            wake_timer.cancel()
            wake_timer = None
            
        release_camera()
        send_event("SLEEP")
        return {"status": "success", "message": "Camera put to sleep"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/wake-camera', methods=['GET'])
@app.route('/wake-camera/<int:num_minutes>', methods=['GET'])
def wake_camera(num_minutes=None):
    global camera_sleeping, wake_timer, last_ball_detection

    if not camera_sleeping:
        return {"status": "error", "message": "Camera is already awake"}, 400

    try:
        # First attempt to initialize the camera
        try:
            initialize_camera()
        except RuntimeError as e:
            return {"status": "error", "message": f"Failed to wake camera: {str(e)}"}, 500
            
        camera_sleeping = False
        last_ball_detection = None  # Reset ball detection timer
        
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
            "message": f"Camera awakened{' for ' + str(num_minutes) + ' minutes' if num_minutes else ' indefinitely'}"
        }, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "camera_sleeping": camera_sleeping,
        "recording": recording
    }), 200

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")
        
        with open(config_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in config file: {config_path}")

def start_flask_server(port: int):
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        print(f"Failed to start server on port {port}: {e}")

def send_event(event_type: str, direction: str = None):
    if event_type not in VALID_EVENTS:
        return
        
    event_data = {
        "event": "STATUS" if event_type in [
            "SYSTEM_START", "CAMERA_ACQUIRED", "FIRST_BALL", "SLEEP",
            "WAKE", "SYSTEM_STOP", "CURRENT_VIEW_SAVED",
            "RECORDING_STARTED", "RECORDING_COMPLETED", "RECORDING_STOPPED"
        ] else "BALL CROSSED",
        "message": VALID_EVENTS[event_type],
        "direction": direction,
        "timestamp": str(datetime.now())
    }

    if not direction:
        event_data.pop("direction")

    event_queue.put(event_data)
    event_list.append(event_data)

    '''
    # Webhook logic (commented out)
    if event_type in config['webhook']:
        webhook_url = config['webhook'][event_type]
    else:
        webhook_url = config['webhook']['default']

    try:
        requests.post(webhook_url, json=event_data)
    except requests.exceptions.RequestException as e:
        print(f"Failed to send webhook: {e}")
    '''

def record_video(num_minutes: int):
    global recording

    try:
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=num_minutes)

        # Define the codec and create VideoWriter object for WebM
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        recordings_dir = Path('recordings')
        recordings_dir.mkdir(exist_ok=True)
        output_filename = recordings_dir / f"recording_{timestamp}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = fps * num_minutes * 60
        out = cv2.VideoWriter(str(output_filename), fourcc, fps, (frame_width, frame_height))

        frame_count = 0

        if not out.isOpened():
            send_event("RECORDING_STOPPED")  # Emit stopped event due to failure
            print("Failed to initialize VideoWriter")
            recording = False
            return

        while recording and frame_count < total_frames and datetime.now() < end_time and not stop_recording_event.is_set():
            if not frame_queue.empty():
                frame = frame_queue.get(timeout=1)
                out.write(frame)
                frame_count += 1
            else:
                time.sleep(0.1)  # Adjust sleep time

        # Determine if recording completed naturally or was stopped
        if datetime.now() >= end_time and not stop_recording_event.is_set():
            send_event("RECORDING_COMPLETED")
        elif stop_recording_event.is_set():
            send_event("RECORDING_STOPPED")

    except Exception as e:
        print(f"Error during recording: {e}")
    finally:
        recording = False
        out.release()
        stop_recording_event.clear()

def stop_current_recording():
    global recording, recording_thread
    if recording and recording_thread:
        stop_recording_event.set()      # Signal the recording thread to stop
        recording_thread.join()         # Wait for the thread to finish
        recording_thread = None
        recording = False
        stop_recording_event.clear()    # Reset the event for future recordings

def wake_timeout(duration_minutes):
    global camera_sleeping, last_ball_detection
    
    if last_ball_detection is None or \
       (datetime.now() - last_ball_detection).total_seconds() > duration_minutes * 60:
        # No ball detected within the timeout period
        with cap_lock:
            camera_sleeping = True
        send_event("SLEEP")
    else:
        # Ball was detected, cancel the timer and stay awake
        global wake_timer
        if wake_timer:
            wake_timer.cancel()
            wake_timer = None

def initialize_camera():
    global cap, video_source
    release_camera()

    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            with cap_lock:
                cap = cv2.VideoCapture(video_source)
                if not cap.isOpened():
                    if attempt < max_retries - 1:
                        print(f"Camera not available, attempt {attempt + 1}/{max_retries}. Retrying...")
                        time.sleep(retry_delay)
                        continue
                    raise RuntimeError("Camera not available after maximum retry attempts")

                # Configure camera settings
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                
                # Verify camera is working by reading a test frame
                ret, test_frame = cap.read()
                if not ret:
                    raise RuntimeError("Camera opened but failed to read test frame")

            print("Camera initialized successfully.")
            return True

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Failed to initialize camera (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
                continue
            with cap_lock:
                cap = None
            raise RuntimeError(f"Failed to initialize camera after {max_retries} attempts: {e}")

def release_camera():
    global cap
    try:
        with cap_lock:
            if cap is not None:
                if cap.isOpened():
                    cap.release()
                cap = None
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"Error during camera release: {e}")
        cap = None

def process_video():
    global cap, model, config, camera_sleeping, recording

    prev_ball_x = None
    crossed_left_to_right = False
    crossed_right_to_left = False
    first_ball_detected = False

    bounding_box_annotator = sv.BoundingBoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    send_event("CAMERA_ACQUIRED")

    # Save initial frame
    with cap_lock:
        ret, frame = cap.read()
    if ret:
        try:
            height, width = frame.shape[:2]
            new_width = 400
            new_height = int(height * (new_width / width))
            resized_frame = cv2.resize(frame, (new_width, new_height))
            
            # Draw rectangle on initial frame
            rect_width = 40
            rect_height = 230
            rect_left = (new_width - rect_width) // 2
            rect_top = (new_height - rect_height) // 2
            rect_right = rect_left + rect_width
            rect_bottom = rect_top + rect_height

            annotated_frame = resized_frame.copy()
            cv2.rectangle(annotated_frame, (rect_left, rect_top), (rect_right, rect_bottom), (0, 0, 255), 2)
            
            output_path = Path(app.static_folder) / 'current-view.png'
            cv2.imwrite(str(output_path), annotated_frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        except Exception as e:
            print(f"Error saving initial frame: {e}")

    while True:
        if camera_sleeping:
            time.sleep(0.1)
            continue
        
        with cap_lock:
            if cap is None or not cap.isOpened():
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

        # Enqueue the raw frame for recording only if recording is active
        if recording:
            try:
                frame_queue.put(frame, timeout=1)
            except queue.Full:
                print("Frame queue is full. Dropping frame.")

        # Perform inference on the frame
        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)
        mask = detections.class_id == 2
        detections = detections[mask]
        
        # Annotate frame for display
        annotated_frame = frame.copy()
        annotated_frame = bounding_box_annotator.annotate(scene=annotated_frame, detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        # Dynamically calculate the rectangle's position at the center
        height, width = frame.shape[:2]
        rect_width = 40  # Define the width of the rectangle
        rect_height = 230  # Define the height of the rectangle
        rect_left = (width - rect_width) // 2
        rect_top = (height - rect_height) // 2
        rect_right = rect_left + rect_width
        rect_bottom = rect_top + rect_height

        cv2.rectangle(annotated_frame, (rect_left, rect_top), (rect_right, rect_bottom), (0, 0, 255), 2)

        if len(detections) > 0:
            global last_ball_detection
            last_ball_detection = datetime.now()

            # Get ball position (center point)
            ball_bbox = detections.xyxy[0]  # Get first detected ball's bounding box
            ball_x = (ball_bbox[0] + ball_bbox[2]) / 2  # Calculate center x-coordinate

            # Check for boundary crossings if we have a previous position
            if prev_ball_x is not None:
                # Ball crosses left boundary -> Right to Left movement
                if prev_ball_x > rect_left > ball_x:
                    send_event("CROSS_RTL", "RIGHT TO LEFT")
                
                # Ball crosses right boundary -> Left to Right movement
                elif prev_ball_x < rect_right < ball_x:
                    send_event("CROSS_LTR", "LEFT TO RIGHT")

            # Update previous ball position
            prev_ball_x = ball_x

            if not first_ball_detected:
                send_event("FIRST_BALL")
                first_ball_detected = True

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    send_event("SYSTEM_STOP")
    release_camera()

def main():
    global config, cap, model, video_source

    os.environ['QT_QPA_PLATFORM'] = 'xcb'

    config = load_config()

    recordings_dir = Path('recordings')
    recordings_dir.mkdir(exist_ok=True)

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
        if recording and recording_thread:
            stop_current_recording()
        release_camera()
        os._exit(0)

if __name__ == "__main__":
    main()