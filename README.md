# Pickleball Events

This repository contains a Python-based project for processing pickleball events and tracking ball movements with real-time web visualization.

## Prerequisites

- Python 3.11.8
- Modern web browser with SSE (Server-Sent Events) support
- Webcam or video file for input

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/fahnub/pickleball-events.git
   cd pickleball-events
   ```

2. Create and activate a virtual environment:

   For Linux/macOS:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   For Windows:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The project uses a `config.json` file to store settings:

```json
{
    "model": {
        "id": "your-model-id",
        "api_key": "your-api-key"
    },
    "rectangle": {
        "left": 1050,
        "right": 1140,
        "top": 0,
        "bottom": 1080
    },
    "webhook": {
        "url": "http://localhost:5000/webhook"
    }
}
```

Key configurations:
- `model`: AI model credentials
- `rectangle`: Boundary coordinates for ball crossing detection
- `webhook`: Event notification endpoint

## Usage

1. First, start the web server:
   ```bash
   python server.py
   ```

2. In a new terminal, run the main script:

   - For default webcam:
     ```bash
     python run.py
     ```

   - For specific webcam:
     ```bash
     python run.py --source 1
     ```

   - For video file:
     ```bash
     python run.py --source path/to/your/video.mp4
     ```

3. Open your web browser and navigate to:
   ```
   http://localhost:5000
   ```

## Features

The application provides:
1. Real-time video processing:
   - Ball detection with bounding boxes
   - Visual crossing boundaries
   - Direction tracking

2. Web Interface:
   - Live event display
   - Crossing event history
   - Timestamp logging
   - Direction indicators

3. Event Tracking:
   - Left-to-right crossing detection
   - Right-to-left crossing detection
   - Real-time event notifications

## Output

The system provides multiple outputs:
1. Video Display:
   - Live video feed
   - Ball detection boxes
   - Boundary rectangle (red)

2. Web Interface:
   - Real-time event updates
   - Event history
   - Crossing direction
   - Timestamps

3. Event Logging:
   - Console output
   - Web interface updates
   - Webhook notifications

Press 'q' to quit the video processing application.

## Troubleshooting

Common Issues:
1. Video Source Problems:
   - Check webcam connections
   - Verify video file path
   - Confirm device permissions

2. Server Issues:
   - Ensure port 5000 is available
   - Check both server and main script are running
   - Verify web browser supports SSE

3. Configuration:
   - Verify config.json exists and is properly formatted
   - Check model credentials
   - Confirm webhook URL is correct

General Checks:
- Using Python 3.11.8
- All requirements installed
- Proper permissions for video access
- Web browser is modern and compatible

## Directory Structure
```
pickleball-events/
├── run.py              # Main video processing script
├── server.py           # Web server for events
├── config.py           # Configuration handler
├── config.json         # Settings file
├── requirements.txt    # Dependencies
└── templates/          # Web interface templates
    └── index.html     # Main web page
```

## Development

To modify the project:
1. Update event detection in `run.py`
2. Modify web interface in `templates/index.html`
3. Adjust server settings in `server.py`
4. Configure boundaries in `config.json`

## Automated Deployment

This project includes an automated deployment script for Ubuntu 22.04 systems (like Intel NUC).

### Prerequisites for Deployment
- Ubuntu 22.04 LTS
- User with sudo privileges
- Internet connection
- USB webcam or video source

### Using the Deployment Script

1. Download the deployment script:
   ```bash
   wget https://raw.githubusercontent.com/fahnub/pickleball-events/main/deploy.sh
   ```

2. Make the script executable:
   ```bash
   chmod +x deploy.sh
   ```

3. Run the deployment script:
   ```bash
   ./deploy.sh
   ```

### What the Deployment Script Does

1. System Setup:
   - Updates system packages
   - Installs system dependencies
   - Configures SSH access
   - Sets up Python 3.11

2. Project Installation:
   - Clones the repository
   - Creates virtual environment
   - Installs Python dependencies
   - Sets up configuration files

3. Service Configuration:
   - Creates systemd services for:
     - Web server (pickleball-server.service)
     - Main application (pickleball-main.service)
   - Enables automatic startup on boot

4. Verification:
   - Checks Python installation
   - Verifies service status
   - Tests web server accessibility

### Post-Deployment

After successful deployment:
1. Web interface is available at: `http://localhost:5000`
2. Services auto-start on system boot
3. SSH access is enabled for remote management

### Service Management

Control the application services:
```bash
# Check status
sudo systemctl status pickleball-server
sudo systemctl status pickleball-main

# Start services
sudo systemctl start pickleball-server
sudo systemctl start pickleball-main

# Stop services
sudo systemctl stop pickleball-server
sudo systemctl stop pickleball-main

# Restart services
sudo systemctl restart pickleball-server
sudo systemctl restart pickleball-main
```

### Troubleshooting Deployment

1. Service Issues:
   - Check service logs:
     ```bash
     sudo journalctl -u pickleball-server
     sudo journalctl -u pickleball-main
     ```
   - Verify permissions in project directory
   - Check configuration file exists

2. Video Source Problems:
   - Verify webcam connection:
     ```bash
     ls /dev/video*
     ```
   - Check webcam permissions:
     ```bash
     sudo usermod -a -G video $USER
     ```

3. Network Issues:
   - Confirm port 5000 is available:
     ```bash
     sudo lsof -i :5000
     ```
   - Check firewall settings:
     ```bash
     sudo ufw status
     ```

### Manual Installation

If you prefer manual installation or the deployment script fails:

1. Install system dependencies:
   ```bash
   sudo apt update && sudo apt upgrade
   sudo apt install python3.11 python3.11-venv git
   ```

2. Clone and setup:
   ```bash
   git clone https://github.com/fahnub/pickleball-events.git
   cd pickleball-events
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Run manually:
   ```bash
   # Terminal 1
   python server.py

   # Terminal 2
   python run.py
   ```