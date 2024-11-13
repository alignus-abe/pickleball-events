import pygame
from pathlib import Path
import logging
from queue import Queue, Empty
import threading
import time

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize pygame mixer
pygame.mixer.init()
pygame.mixer.set_num_channels(8)  # Allow up to 8 simultaneous sounds

class SoundManager:
    def __init__(self):
        self.sound_cache = {}
        self.sound_queue = Queue()
        self.running = True
        self.worker_thread = threading.Thread(target=self._process_sound_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def _load_sound(self, sound_name):
        if sound_name not in self.sound_cache:
            sound_path = Path('sounds') / f"{sound_name}.wav"
            if not sound_path.exists():
                logger.error(f"Sound file not found: {sound_path}")
                return None
            self.sound_cache[sound_name] = pygame.mixer.Sound(str(sound_path))
        return self.sound_cache[sound_name]

    def _process_sound_queue(self):
        while self.running:
            try:
                sound_name = self.sound_queue.get(timeout=1)
                sound = self._load_sound(sound_name)
                if sound:
                    sound.play()
                    logger.debug(f"Playing sound: {sound_name}")
            except Empty:
                continue

    def play_sound(self, sound_name):
        """Queue a sound to be played"""
        self.sound_queue.put(sound_name)
        logger.debug(f"Queued sound: {sound_name}")

    def stop(self):
        """Stop the sound manager"""
        self.running = False
        pygame.mixer.quit()

# Create global sound manager instance
sound_manager = SoundManager()

def play_sound(sound_name):
    """Global function to play a sound"""
    sound_manager.play_sound(sound_name) 