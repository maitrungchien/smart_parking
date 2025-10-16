# model_loader.py
import torch
# Tải mô hình YOLO một lần
yolo_LP_detect = torch.hub.load('yolov5', 'custom', path='C:/Users/Admin/Documents/Smart_Parking-main/Smart_Parking-main/model/LP_detector.pt', force_reload=True, source='local')
yolo_license_plate = torch.hub.load('yolov5', 'custom', path='C:/Users/Admin/Documents/Smart_Parking-main/Smart_Parking-main/model/LP_ocr.pt', force_reload=True, source='local')
yolo_license_plate.conf = 0.70  # Đặt độ tin cậy nếu cần

print("Đã tải mô hình YOLO thành công.")
