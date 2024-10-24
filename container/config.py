import json
from typing import Dict, Any

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    with open(config_path, 'r') as config_file:
        return json.load(config_file)
