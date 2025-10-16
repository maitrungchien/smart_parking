import cv2

for index in range(3):  # Thử lần lượt 3 camera
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"Device index {index} could not be opened.")
        continue
    print(f"Testing device index {index}. Press 'q' to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Device index {index} failed to capture.")
            break
        cv2.imshow(f"Camera {index}", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):  # Nhấn 'q' để thoát
            break
    cap.release()
    cv2.destroyAllWindows()
