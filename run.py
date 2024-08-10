import argparse
from inference import get_model
import supervision as sv
import cv2
from config import load_config

def get_video_source(source):
    if source.isdigit():
        return int(source)
    return source

def main(video_source: str):
    config = load_config()

    model = get_model(model_id=config['model']['id'], api_key=config['model']['api_key'])

    video_source = get_video_source(video_source)
    cap = cv2.VideoCapture(video_source)

    if not cap.isOpened():
        print(f"Error: Could not open video source {video_source}")
        return

    RECT_LEFT = config['rectangle']['left']
    RECT_RIGHT = config['rectangle']['right']
    RECT_TOP = config['rectangle']['top']
    RECT_BOTTOM = config['rectangle']['bottom']

    prev_ball_x = None
    crossed_left_to_right = False
    crossed_right_to_left = False

    bounding_box_annotator = sv.BoundingBoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)

        annotated_frame = bounding_box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        cv2.rectangle(annotated_frame, (RECT_LEFT, RECT_TOP), (RECT_RIGHT, RECT_BOTTOM), (0, 0, 255), 2)

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

        cv2.imshow('Pickleball Tracking', annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pickleball Tracking Script")
    parser.add_argument("--source", type=str, default="0", help="Video source (0 for default webcam, 1,2,etc. for other webcams, or path to video file)")
    args = parser.parse_args()

    main(args.source)