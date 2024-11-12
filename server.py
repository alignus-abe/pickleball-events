from flask import Flask, render_template, Response, request, send_from_directory
import json
import queue

app = Flask(__name__, static_folder='static', static_url_path='/static')
event_queue = queue.Queue()

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

@app.route('/static/current-view.png')
def serve_current_view():
    return send_from_directory(app.static_folder, 'current-view.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)