from flask import Flask, render_template, Response, send_from_directory, jsonify
import json
import queue
import threading
from pathlib import Path
import cv2
from datetime import datetime, timedelta
import time
import os
from collections import deque
import logging

app = Flask(__name__, static_folder='static', static_url_path='/static')
event_queue = queue.Queue()
event_list = deque(maxlen=500)
frame_queue = queue.Queue(maxsize=1000)
stop_recording_event = threading.Event()

config = None
cap = None
recording = False
recording_thread = None

VALID_EVENTS = {
    "SYSTEM_START": "SYSTEM STARTED",
    "CAMERA_ACQUIRED": "CAMERA ACQUIRED",
    "SYSTEM_STOP": "SYSTEM STOPPED",
    "CURRENT_VIEW_SAVED": "SAVED CURRENT VIEW",
    "RECORDING_STARTED": "RECORDING STARTED",
    "RECORDING_COMPLETED": "RECORDING COMPLETED",
    "RECORDING_STOPPED": "RECORDING STOPPED"
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Global lock for camera access
cap_lock = threading.Lock()

@app.route('/')
def index():
    events = list(event_list)
    return render_template('index.html', initial_events=events)

@app.route('/events')
def events_stream():
    def event_stream():
        while True:
            try:
                message = event_queue.get(timeout=1)
                yield f"data: {json.dumps(message)}\n\n"
            except queue.Empty:
                # Send a keepalive message to maintain the connection
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
    if not cap or not cap.isOpened():
        return "Camera not initialized", 500

    ret, frame = None, None
    with cap_lock:
        ret, frame = cap.read()
    
    if not ret:
        logging.error("Failed to capture frame")
        return "Failed to capture frame", 500

    try:
        output_path = Path(app.static_folder) / 'current-view.png'
        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        send_event("CURRENT_VIEW_SAVED")
        logging.info("Frame saved successfully")
        return "Frame saved successfully", 200
    except Exception as e:
        logging.error(f"Error saving frame: {e}")
        return f"Error saving frame: {e}", 500

@app.route('/start-new-recording/<int:num_minutes>')
def start_new_recording(num_minutes):
    global recording_thread, cap, frame_queue, recording

    if num_minutes <= 0:
        return {"status": "error", "message": "Recording duration must be positive"}, 400

    if cap is None or not cap.isOpened():
        return {"status": "error", "message": "Camera not available"}, 500

    try:
        if recording and recording_thread:
            stop_recording_event.set()
            recording_thread.join()

        with frame_queue.mutex:
            frame_queue.queue.clear()

        stop_recording_event.clear()

        recording = True
        recording_thread = threading.Thread(
            target=record_video, 
            args=(num_minutes,),
            daemon=True
        )
        recording_thread.start()

        time.sleep(0.5)

        send_event("RECORDING_STARTED")
        logging.info(f"Recording started for {num_minutes} minutes")
        return {"status": "success", "message": f"Recording started for {num_minutes} minutes"}, 200
    except Exception as e:
        logging.error(f"Error starting recording: {e}")
        return {"status": "error", "message": str(e)}, 500

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "recording": recording
    }), 200

def send_event(event_type: str):
    if event_type not in VALID_EVENTS:
        return
    
    event_data = {
        "event": "STATUS" if event_type in [
            "SYSTEM_START", "CAMERA_ACQUIRED", "SYSTEM_STOP", 
            "CURRENT_VIEW_SAVED", "RECORDING_STARTED", 
            "RECORDING_COMPLETED", "RECORDING_STOPPED"
        ] else "RECORDING",
        "message": VALID_EVENTS[event_type],
        "timestamp": datetime.now().isoformat()
    }

    event_queue.put(event_data)
    event_list.append(event_data)

def record_video(num_minutes: int):
    global recording

    try:
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=num_minutes)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        recordings_dir = Path('recordings')
        recordings_dir.mkdir(exist_ok=True)
        output_filename = recordings_dir / f"recording_{timestamp}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = max(int(cap.get(cv2.CAP_PROP_FPS)), 30)
        total_frames = fps * num_minutes * 60
        out = cv2.VideoWriter(str(output_filename), fourcc, fps, (frame_width, frame_height))

        frame_count = 0

        if not out.isOpened():
            send_event("RECORDING_STOPPED")
            logging.error("Failed to initialize VideoWriter")
            recording = False
            return

        while recording and frame_count < total_frames and datetime.now() < end_time and not stop_recording_event.is_set():
            if not frame_queue.empty():
                frame = frame_queue.get(timeout=1)
                out.write(frame)
                frame_count += 1
            else:
                time.sleep(0.1)

        if datetime.now() >= end_time and not stop_recording_event.is_set():
            send_event("RECORDING_COMPLETED")
            logging.info("Recording completed")
        elif stop_recording_event.is_set():
            send_event("RECORDING_STOPPED")
            logging.info("Recording stopped manually")

    except Exception as e:
        logging.error(f"Error during recording: {e}")
    finally:
        recording = False
        out.release()
        stop_recording_event.clear()

def process_video():
    global cap, recording

    send_event("CAMERA_ACQUIRED")
    logging.info("Camera acquired")

    while True:
        with cap_lock:
            ret, frame = cap.read()

        if not ret:
            logging.error("Failed to read frame")
            time.sleep(1)
            continue

        if recording:
            try:
                frame_queue.put(frame, timeout=1)
            except queue.Full:
                logging.warning("Frame queue is full. Dropping frame.")

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    send_event("SYSTEM_STOP")
    logging.info("System stopped")

def start_flask_server(port: int):
    app.run(host='0.0.0.0', port=port, threaded=True)

def load_config():
    global config
    config_path = Path('config.json')
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        logging.info("Configuration loaded from config.json")
    else:
        logging.warning("config.json not found. Using default settings.")

def main():
    global config, cap

    load_config()

    recordings_dir = Path('recordings')
    recordings_dir.mkdir(exist_ok=True)

    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)

    video_source = int(config['video_source']) if config['video_source'].isdigit() else config['video_source']
    cap = cv2.VideoCapture(video_source)
    
    # Set codec to MJPG for better high-resolution support
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    # Force 1920x1080 resolution and 60fps regardless of config settings
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 60)

    # Verify the actual settings
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
    
    logging.info(f"Camera initialized at {actual_width}x{actual_height} @ {actual_fps}fps")

    if not cap.isOpened():
        logging.critical(f"Failed to open video source: {video_source}")
        raise RuntimeError(f"Failed to open video source: {video_source}")

    if actual_width != 1920 or actual_height != 1080:
        logging.warning(f"Camera does not support 1920x1080. Current resolution: {actual_width}x{actual_height}")
    
    if actual_fps != 60:
        logging.warning(f"Camera does not support 60fps. Current FPS: {actual_fps}")

    server_thread = threading.Thread(target=start_flask_server, args=(config['server_port'],))
    server_thread.daemon = True
    server_thread.start()
    logging.info(f"Started server on port {config['server_port']}")

    send_event("SYSTEM_START")

    video_thread = threading.Thread(target=process_video)
    video_thread.daemon = True
    video_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        if recording and recording_thread:
            stop_recording_event.set()
            recording_thread.join()
        cap.release()
        os._exit(0)

if __name__ == "__main__":
    main()