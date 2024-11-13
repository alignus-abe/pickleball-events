from flask import Flask, jsonify
from utils.sound import play_sound
import logging

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/play/<sound_name>', methods=['POST'])
def play_sound_endpoint(sound_name):
    """Endpoint to play a sound by name"""
    try:
        play_sound(sound_name)
        return jsonify({"status": "success", "message": f"Playing sound: {sound_name}"}), 200
    except Exception as e:
        logger.error(f"Error playing sound {sound_name}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sounds', methods=['GET'])
def list_sounds():
    """List all available sounds"""
    try:
        from pathlib import Path
        sounds_dir = Path('sounds')
        sounds = [f.stem for f in sounds_dir.glob('*.wav')]
        return jsonify({"status": "success", "sounds": sounds}), 200
    except Exception as e:
        logger.error(f"Error listing sounds: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002) 