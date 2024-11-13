#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import datetime
import requests
from utils.sound import play_sound
import time

def main():
    parser = argparse.ArgumentParser(description="Control Pickleball Detection Service")
    parser.add_argument("command", choices=["sleep", "wake"], help="Command to send to the service")
    args = parser.parse_args()

    control_file = Path("/tmp/pickleball_control.json")
    config_file = Path("config.json")
    
    if not control_file.exists():
        print("Control file not found. Is the service running?")
        return
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    with open(control_file, "r") as f:
        state = json.load(f)
    
    if args.command == "sleep":
        state["active"] = False
        message = "sleeping"
    else:  # wake
        state["active"] = True
        state["last_ball_detection"] = None
        message = "waking"
    
    webhook_data = {
        "event": "status",
        "message": message,
        "timestamp": str(datetime.datetime.now())
    }
    
    for webhook_url in config['webhook']['urls']:
        try:
            requests.post(webhook_url, json=webhook_data)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send webhook to {webhook_url}: {e}")

    # Play sound if enabled
    if config.get('sound_sleep_states', False):
        print(f"Playing sleep/wake sound (sound_sleep_states is enabled)")
        play_sound("drone")
        time.sleep(1)
    else:
        print(f"Not playing sound (sound_sleep_states is {config.get('sound_sleep_states', False)})")
    
    with open(control_file, "w") as f:
        json.dump(state, f)
    
    print(f"Service {args.command} command sent successfully")

if __name__ == "__main__":
    main() 