import cv2
import supervision as sv
from inference import get_model
from config import load_config

config = load_config()

model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])

RECT_LEFT = config['rectangle']['left']
RECT_RIGHT = config['rectangle']['right']
RECT_TOP = config['rectangle']['top']
RECT_BOTTOM = config['rectangle']['bottom']

prev_ball_x = None
crossed_left_to_right = False
crossed_right_to_left = False

def process_video(video_source: str):
    global prev_ball_x, crossed_left_to_right, crossed_right_to_left

    cap = cv2.VideoCapture(video_source)

    if not cap.isOpened():
        print(f"Error: Could not open video source {video_source}")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)

        if len(detections) > 0:
            ball_x = detections.xyxy[0][0]

            if prev_ball_x is not None:
                if prev_ball_x < RECT_LEFT < ball_x and not crossed_left_to_right:
                    print("left to right")
                    crossed_left_to_right = True
                    crossed_right_to_left = False
                elif prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left:
                    print("right to left")
                    crossed_right_to_left = True
                    crossed_left_to_right = False

            prev_ball_x = ball_x

    cap.release()

if __name__ == "__main__":
    process_video("/data/test.mp4")
