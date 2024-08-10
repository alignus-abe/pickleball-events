# Pickleball Events

This repository contains a Python-based project for processing pickleball events.

## Prerequisites

- Python 3.11.8
- Video file named `pickleball.mp4` in the project directory

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

## Usage

1. Ensure you have a video file named `pickleball.mp4` in the project directory.

2. Run the main script:
   ```
   python run.py
   ```

## Output

The script will process the video and provide output based on the pickleball events detected.

## Troubleshooting

If you encounter any issues, make sure:
- You're using Python 3.11.8
- All requirements are correctly installed
- The video file is named correctly and in the right location