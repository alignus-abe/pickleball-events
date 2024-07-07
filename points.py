import cv2

frame = None
point_coordinates = []

def click_event(event, x, y, flags, param):
    global frame, point_coordinates
    if event == cv2.EVENT_LBUTTONDOWN:
        point_coordinates.append((x, y))
        cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
        cv2.imshow('Video', frame)
        print(f"Clicked coordinates: ({x}, {y})")

def get_coordinates(video_path):
    global frame
    cap = cv2.VideoCapture(video_path)
    
    cv2.namedWindow('Video')
    cv2.setMouseCallback('Video', click_event)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        cv2.imshow('Video', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            if point_coordinates:
                print("Selected coordinates:")
                for i, coord in enumerate(point_coordinates, 1):
                    print(f"Point {i}: {coord}")
            else:
                print("No points selected yet.")

    cap.release()
    cv2.destroyAllWindows()

    return point_coordinates

video_path = 'pickleball.mp4'
coordinates = get_coordinates(video_path)
print("Final selected coordinates:", coordinates)