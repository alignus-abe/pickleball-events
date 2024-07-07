from inference import get_model
import supervision as sv
import cv2
import asyncio
import websockets
import json

model = get_model(model_id="pickleball-vision/1", api_key="NaHUxOSMxQUvgg9tfhcE")

video_path = "pickleball.mp4"

clients = set()

async def register(websocket):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)

async def broadcast(message):
    for client in clients:
        try:
            await client.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            pass

async def process_video():
    cap = cv2.VideoCapture(video_path)

    bounding_box_annotator = sv.BoundingBoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    rect_left = 1050
    rect_right = 1140

    prev_ball_x = None
    crossed_left_to_right = False
    crossed_right_to_left = False

    while cap.isOpened():
        ret, frame = cap.read()

        if not ret:
            break

        results = model.infer(frame)[0]
        detections = sv.Detections.from_inference(results)

        annotated_frame = bounding_box_annotator.annotate(scene=frame, detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections)

        cv2.rectangle(annotated_frame, (rect_left, 0), (rect_right, 1080), (0, 0, 255), 2)

        if len(detections) > 0:
            ball_x = detections.xyxy[0][0]

            if prev_ball_x is not None:
                if prev_ball_x < rect_left < ball_x and not crossed_left_to_right:
                    await broadcast({"direction": "left_to_right"})
                    crossed_left_to_right = True
                    crossed_right_to_left = False
                elif prev_ball_x > rect_right > ball_x and not crossed_right_to_left:
                    await broadcast({"direction": "right_to_left"})
                    crossed_right_to_left = True
                    crossed_left_to_right = False

            prev_ball_x = ball_x

        cv2.imshow('Video Inference', annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        await asyncio.sleep(0.01)

    cap.release()
    cv2.destroyAllWindows()

async def main():
    server = await websockets.serve(register, "localhost", 8765)
    await asyncio.gather(server.wait_closed(), process_video())

if __name__ == "__main__":
    asyncio.run(main())