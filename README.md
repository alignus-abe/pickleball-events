# Pickleball Events

This repository contains a Python-based project for processing pickleball events and tracking ball movements.

## Prerequisites

- Python 3.11.8

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/fahnub/pickleball-events.git
   cd pickleball-events
   ```

2. Create and activate a virtual environment:

   For Linux:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

   For Windows:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Configuration

The project uses a `config.json` file to store various settings. You can modify this file to adjust the model parameters and the rectangle coordinates for ball crossing detection.

## Usage

Run the main script with the desired video source:

- For the default webcam:
  ```
  python run.py
  ```

- For a specific webcam (e.g., the second one):
  ```
  python run.py --source 1
  ```

- For a video file:
  ```
  python run.py --source path/to/your/video.mp4
  ```

## Output

The script will process the video input and:
1. Display the video feed with bounding boxes around detected balls
2. Show a red rectangle indicating the crossing boundaries
3. Print messages when the ball crosses the specified boundaries

Press 'q' to quit the application.

## Troubleshooting

If you encounter any issues, make sure:
- You're using Python 3.11.8
- All requirements are correctly installed
- The `config.json` file is present and correctly formatted
- You have the necessary permissions to access the webcam or video file