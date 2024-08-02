from inference import get_model
import supervision as sv
import cv2

model = get_model(model_id="pickleball-vision/1", api_key="NaHUxOSMxQUvgg9tfhcE")

video_path = "pickleball.mp4"

cap = cv2.VideoCapture(video_path)

RECT_LEFT = 1050
RECT_RIGHT = 1140

prev_ball_x = None
crossed_left_to_right = False
crossed_right_to_left = False

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    results = model.infer(frame)[0]
    detections = sv.Detections.from_inference(results)

    if len(detections) > 0:
        ball_x = detections.xyxy[0][0]

        if prev_ball_x is not None:
            if prev_ball_x < RECT_LEFT < ball_x and not crossed_left_to_right:
                print("Ball crossed from left to right")
                crossed_left_to_right = True
                crossed_right_to_left = False
            elif prev_ball_x > RECT_RIGHT > ball_x and not crossed_right_to_left:
                print("Ball crossed from right to left")
                crossed_right_to_left = True
                crossed_left_to_right = False

        prev_ball_x = ball_x

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()