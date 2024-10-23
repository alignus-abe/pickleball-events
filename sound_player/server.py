from flask import Flask, render_template
import subprocess
import threading
import os

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/play')
def play_audio():
    audio_file = os.path.join(os.getcwd(), 'sample.wav')

    def play_audio_thread():
        subprocess.call(['paplay', audio_file])

    threading.Thread(target=play_audio_thread).start()
    return "Playing audio..."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)