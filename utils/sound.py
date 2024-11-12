import pygame
from pathlib import Path
import logging

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def play_sound(sound_name):
    """Play a sound file from the sounds directory"""
    try:
        # Initialize mixer if not already initialized
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            logger.debug("Initialized pygame mixer")

        sound_path = Path('sounds') / f"{sound_name}.wav"
        logger.debug(f"Attempting to play sound: {sound_path}")
        
        if not sound_path.exists():
            logger.error(f"Sound file not found: {sound_path}")
            return
            
        sound = pygame.mixer.Sound(str(sound_path))
        sound.play()
        logger.debug(f"Successfully played sound: {sound_name}")
        
        # Optional: wait for sound to finish
        pygame.time.wait(int(sound.get_length() * 1000))
        
    except Exception as e:
        logger.error(f"Error playing sound {sound_name}: {e}") 