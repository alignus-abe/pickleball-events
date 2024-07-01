from inference import get_model
import supervision as sv
import cv2

model = get_model(model_id="pickleball-vision/1")

video_path = "pickleball.mp4"

cap = cv2.VideoCapture(video_path)

bounding_box_annotator = sv.BoundingBoxAnnotator()
label_annotator = sv.LabelAnnotator()

while cap.isOpened():
    ret, frame = cap.read()

    if not ret:
        break

    results = model.infer(frame)[0]
    detections = sv.Detections.from_inference(results)

    annotated_frame = bounding_box_annotator.annotate(scene=frame, detections=detections)
    annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

    cv2.imshow('Video Inference', annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()