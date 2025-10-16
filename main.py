import tkinter as tk  # Nhập thư viện tkinter để xây dựng giao diện đồ họa
from PIL import Image, ImageTk  # Nhập thư viện PIL để xử lý hình ảnh
import cv2  # Nhập thư viện OpenCV để làm việc với video và camera
import datetime  # Nhập thư viện datetime để xử lý thời gian
import numpy as np
import torch
import function.helper as helper
import math 
import function.utils_rotate as utils_rotate
from IPython.display import display
from model_loader import yolo_LP_detect, yolo_license_plate
import os
import time
import argparse
import mysql.connector
import warnings
import io
import serial
import threading
import sys
from tkinter import ttk, messagebox
warnings.simplefilter("ignore", category=FutureWarning)

esp32_serial = serial.Serial('COM4', 115200)

# Kết nối đến cơ sở dữ liệu MySQL
def connectDB():
    try:
        con = mysql.connector.connect(
            host='localhost',
            user='chicago',
            password='Chicago1203@',
            database='license'
        )
        return con
    except mysql.connector.Error as err:
        write_log(f"Error: {err}")
        return None

# Kiểm tra biển số xe đã tồn tại trong database chưa
def checkNp(number_plate):
    con = connectDB()
    if con is None:
        return -1
    cursor = con.cursor()
    sql = "SELECT COUNT(*) FROM Numberplate WHERE number_plate = %s"
    cursor.execute(sql, (number_plate,))
    result = cursor.fetchone()[0]
    cursor.close()
    con.close()
    return result

# Kiểm tra trạng thái bản ghi gần nhất của biển số xe
def checkNpStatus(rfid_tag):
    con = connectDB()
    if con is None:
        return None
    
    cursor = con.cursor()
    
    # Truy vấn để lấy toàn bộ bản ghi gần nhất của xe với biển số tương ứng
    sql = "SELECT * FROM Numberplate WHERE rfid_tag = %s ORDER BY date_in DESC LIMIT 1"
    cursor.execute(sql, (rfid_tag,))
    result = cursor.fetchone()
    
    cursor.close()
    con.close()
    
    # Trả về bản ghi đầy đủ nếu tồn tại, nếu không thì trả về None
    return result

# Thêm bản ghi mới cho xe vào bãi
def insertNp(rfid_tag, number_plate, crop_img):
    if crop_img is None or crop_img.size == 0:
        write_log("Ảnh biển số không hợp lệ.")
        return  # Nếu ảnh không hợp lệ, không thực hiện lưu trữ

    con = connectDB()
    if con is None:
        return
    cursor = con.cursor()

    # Chuyển ảnh biển số thành nhị phân (BLOB)
    image_binary_in = convert_image_to_binary(crop_img)
    
    if image_binary_in:
        # Lưu biển số và ảnh biển số khi xe vào
        sql = "INSERT INTO Numberplate (rfid_tag, number_plate, status, date_in, in_plate_image) VALUES (%s, %s, %s, %s, %s)"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(sql, (rfid_tag, number_plate, 1, now, image_binary_in))  # Trạng thái 1 nghĩa là xe đang trong bãi
        con.commit()

        cursor.close()
        con.close()
        write_log(f"Ảnh biển số khi vào bãi đã được lưu cho xe {number_plate}.")
    else:
        write_log("Lỗi khi chuyển ảnh biển số vào sang nhị phân!")

# Cập nhật bản ghi khi xe ra khỏi bãi
def updateNp(Id, number_plate, crop_img_out):
    con = connectDB()
    if con is None:
        return
    cursor = con.cursor()

    # Chuyển ảnh biển số thành nhị phân (BLOB)
    image_binary_out = convert_image_to_binary(crop_img_out)
    
    if image_binary_out:
        # Cập nhật ảnh biển số khi xe ra bãi
        sql = "UPDATE Numberplate SET status = 0, date_out = %s, out_plate_image = %s WHERE number_plate = %s AND status = 1"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(sql, (now, image_binary_out, number_plate))  # Trạng thái 0 nghĩa là xe đã ra khỏi bãi
        con.commit()

        cursor.close()
        con.close()
        write_log(f"Ảnh biển số khi xe ra bãi đã được lưu cho xe {number_plate}.")
    else:
        write_log("Lỗi khi chuyển ảnh biển số ra sang nhị phân!")
def updateOutTime(cursor, license_plate, out_time):
    query = "UPDATE xe SET thoi_gian_ra = %s WHERE bien_so = %s"
    cursor.execute(query, (out_time, license_plate))

def get_in_plate_image_from_db(con, rfid_tag):
    # Loại bỏ khoảng trắng thừa (nếu có)
    rfid_tag = rfid_tag.strip()

    # Kết nối đến cơ sở dữ liệu
    cursor = con.cursor()  # Tạo con trỏ để thực thi truy vấn

    try:
        # Truy vấn cơ sở dữ liệu để lấy ảnh biển số theo mã thẻ RFID
        sql = "SELECT in_plate_image FROM Numberplate WHERE rfid_tag = %s AND status = 1"
        cursor.execute(sql, (rfid_tag,))  # Thực thi câu lệnh với mã thẻ RFID

        # Lấy kết quả truy vấn
        result = cursor.fetchone()

        # Đóng kết nối
        cursor.close()
        con.close()

        if result and result[0]:
            # Trả về ảnh nhị phân nếu có
            return result[0]
        else:
            write_log(f"Không tìm thấy ảnh biển số cho mã RFID {rfid_tag}")
            return None
    except Exception as e:
        write_log(f"Lỗi khi truy vấn cơ sở dữ liệu: {e}")
        cursor.close()  # Đảm bảo đóng con trỏ nếu có lỗi
        con.close()  # Đảm bảo đóng kết nối
        return None

# Chuyển ảnh sang nhị phân (BLOB)
def convert_image_to_binary(image):
    is_success, buffer = cv2.imencode(".jpg", image)
    if is_success:
        return buffer.tobytes()
    return None
def convert_binary_to_image(binary_data):
    # Hàm chuyển đổi nhị phân thành ảnh
    image = cv2.imdecode(np.frombuffer(binary_data, np.uint8), cv2.IMREAD_COLOR)
    return image

def save_binary_image_to_jpg(binary_data, output_filename):
    try:
        # Chuyển đổi nhị phân thành đối tượng ảnh
        image = Image.open(io.BytesIO(binary_data))
        
        # Lưu ảnh dưới dạng JPG
        image.save(output_filename, 'JPEG')
        write_log(f"Ảnh đã được lưu thành công dưới tên: {output_filename}")
    except Exception as e:
        write_log(f"Lỗi khi chuyển ảnh nhị phân sang JPG: {e}")

def reset_esp32(esp32_serial):
    """Gửi lệnh RESET tới ESP32 qua Serial để reset thiết bị."""
    try:
        esp32_serial.write(b"RESET\n")  # Gửi lệnh reset
        write_log("Đã gửi lệnh RESET tới ESP32.")
    except serial.SerialException as e:
        write_log(f"Lỗi khi gửi lệnh RESET: {e}")

def update_button_state(state):
    """Cập nhật trạng thái của nút dựa trên tín hiệu từ ESP32."""
    if state == "SERVO_IN_OPEN":
        btn_in.config(bg="green")  # Mở: màu xanh
    elif state == "SERVO_IN_CLOSED":
        btn_in.config(bg="red")  # Đóng: màu đỏ
    elif state == "SERVO_OUT_OPEN":
        btn_out.config(bg="green")  # Mở: màu xanh
    elif state == "SERVO_OUT_CLOSED":
        btn_out.config(bg="red")  # Đóng: màu đỏ

def connect_to_esp32(port='COM4', baudrate=115200, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            esp32_serial = serial.Serial(port, baudrate)
            write_log(f"Đã kết nối thành công với ESP32 trên {port} ở baudrate {baudrate}.")
            reset_esp32(esp32_serial)
            write_log("Khởi động lại chương trình...")
            python = sys.executable
            os.execl(python, python, *sys.argv)
            return esp32_serial  # Trả về đối tượng Serial nếu kết nối thành công
        except serial.SerialException as e:
            write_log(f"Kết nối thất bại với ESP32 (thử lần {attempt}/{retries}): {e}")
            if attempt < retries:
                write_log(f"Đang thử lại trong {delay} giây...")
                time.sleep(delay)
            else:
                write_log("Không thể kết nối với ESP32. Tự động kết nối lại sau 5 giây.")
                time.sleep(5)
                connect_to_esp32()

# Lắng nghe dữ liệu từ ESP32
def listen_to_esp32():
    """Luồng lắng nghe tín hiệu từ ESP32 và cập nhật trạng thái nút."""
    try:
        while True:
            if esp32_serial.in_waiting > 0:
                data = esp32_serial.readline().decode('utf-8').strip()
                if data.startswith("SERVO"):  # Kiểm tra tín hiệu trạng thái servo
                    update_button_state(data)  # Cập nhật trạng thái nút
                elif data.startswith("IN,"):  # Xử lý tín hiệu xe vào
                    rfid_tag = data.split(",")[1]
                    write_log(f"Xe vào với thẻ RFID: {rfid_tag}")
                    check_in(rfid_tag)
                elif data.startswith("OUT,"):  # Xử lý tín hiệu xe ra
                    rfid_tag = data.split(",")[1]
                    write_log(f"Xe ra với thẻ RFID: {rfid_tag}")
                    check_out(rfid_tag)
            time.sleep(0.1)
    except serial.SerialException as e:
        write_log(f"Lỗi kết nối Serial: {e}")
    except Exception as e:
        write_log(f"Lỗi không mong muốn: {e}")
    finally:
        if esp32_serial:
            esp32_serial.close()
            write_log("Đã đóng kết nối Serial với ESP32.")
            connect_to_esp32()
            pass

# Tạo luồng để lắng nghe ESP32 và tránh chặn giao diện Tkinter
esp32_thread = threading.Thread(target=listen_to_esp32)
esp32_thread.daemon = True  # Đặt luồng là daemon để tự thoát khi chương trình dừng
esp32_thread.start()

# Khởi tạo cửa sổ giao diện Tkinter
root = tk.Tk()
root.title("Bãi Đỗ Xe Thông Minh")
root.geometry("1200x750")  # Kích thước cửa sổ lớn hơn để cân đối
root.configure(bg="sky blue")

# Khung tiêu đề
title_label = tk.Label(root, text="BÃI ĐỖ XE THÔNG MINH", font=("Arial", 20, "bold"), bg="sky blue")
title_label.pack(pady=10)

# Khởi tạo camera với OpenCV
#cap_in = cv2.VideoCapture(0)  # Camera vào (đặt 0 để sử dụng camera mặc định)
cap_in = cv2.VideoCapture(1)  # Camera ra (đặt 1 nếu có camera thứ hai, nếu không đặt cả hai đều là 0)
cap_out = cv2.VideoCapture(2)  # Camera ra (đặt 1 nếu có camera thứ hai, nếu không đặt cả hai đều là 0)

# Khung camera vào và ra
frame_cameras = tk.Frame(root, bg="white", highlightbackground="black", highlightthickness=1)
frame_cameras.place(x=20, y=70, width=700, height=550)

# Khung camera vào
camera_in_frame = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
camera_in_frame.place(x=20, y=20, width=320, height=240)
camera_in_label = tk.Label(camera_in_frame, text="CAMERA VÀO", font=("Arial", 12, "bold"), bg="white")
camera_in_label.pack(anchor="n")
camera_in_image = tk.Label(camera_in_frame, bg="black")
camera_in_image.pack(expand=True)

# Khung hiển thị ảnh biển số xe dưới camera vào
plate_image_frame = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
plate_image_frame.place(x=20, y=280, width=320, height=200)
plate_image_label = tk.Label(plate_image_frame, text="ẢNH BIỂN SỐ XE VÀO", font=("Arial", 12, "bold"), bg="white")
plate_image_label.pack(anchor="n")
plate_image_display = tk.Label(plate_image_frame, bg="light gray")
plate_image_display.pack(expand=True)

# Khung mã biển số xe dưới camera vào
license_plate_frame = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
license_plate_frame.place(x=20, y=500, width=320, height=40)  # Đặt vị trí và tăng kích thước
license_plate_label = tk.Label(license_plate_frame, text="MÃ BIỂN SỐ XE VÀO", font=("Arial", 12, "bold"), bg="white")
license_plate_label.pack(side="left", padx=5)
license_plate_display = tk.Label(license_plate_frame, text="Chưa xác định", font=("Arial", 12), bg="light gray", width=20)
license_plate_display.pack(side="right", padx=5)

# Khung camera ra
camera_out_frame = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
camera_out_frame.place(x=360, y=20, width=320, height=240)
camera_out_label = tk.Label(camera_out_frame, text="CAMERA RA", font=("Arial", 12, "bold"), bg="white")
camera_out_label.pack(anchor="n")
camera_out_image = tk.Label(camera_out_frame, bg="black")
camera_out_image.pack(expand=True)

# Khung hiển thị ảnh biển số xe dưới camera ra
plate_image_frame_out = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
plate_image_frame_out.place(x=360, y=280, width=320, height=200)
plate_image_label_out = tk.Label(plate_image_frame_out, text="ẢNH BIỂN SỐ XE RA", font=("Arial", 12, "bold"), bg="white")
plate_image_label_out.pack(anchor="n")
plate_image_display_out = tk.Label(plate_image_frame_out, bg="light gray")
plate_image_display_out.pack(expand=True)

# Khung mã biển số xe dưới camera ra
license_plate_frame_out = tk.Frame(frame_cameras, bg="white", highlightbackground="black", highlightthickness=1)
license_plate_frame_out.place(x=360, y=500, width=320, height=40)  # Đặt vị trí và tăng kích thước
license_plate_label_out = tk.Label(license_plate_frame_out, text="MÃ BIỂN SỐ XE RA", font=("Arial", 12, "bold"), bg="white")
license_plate_label_out.pack(side="left", padx=5)
license_plate_display_out = tk.Label(license_plate_frame_out, text="Chưa xác định", font=("Arial", 12), bg="light gray", width=20)
license_plate_display_out.pack(side="right", padx=5)

# Khung thông tin
info_frame = tk.Frame(root, bg="white", highlightbackground="black", highlightthickness=1)
info_frame.place(x=750, y=70, width=400, height=350)

time_label = tk.Label(info_frame, text="", font=("Arial", 14), bg="white")
time_label.grid(row=0, column=0, columnspan=2, pady=(20, 10))

label_veh_num = tk.Label(info_frame, text="SỐ XE", font=("Arial", 12), bg="white")
label_veh_num.grid(row=1, column=0, pady=10, sticky="e")
entry_veh_num = tk.Entry(info_frame, font=("Arial", 12), width=15, bg="light green")
entry_veh_num.grid(row=1, column=1, pady=10, sticky="w")

label_in_time = tk.Label(info_frame, text="VÀO", font=("Arial", 12), bg="white")
label_in_time.grid(row=2, column=0, pady=10, sticky="e")
entry_in_time = tk.Entry(info_frame, font=("Arial", 12), width=20)
entry_in_time.grid(row=2, column=1, pady=10, sticky="w")

label_out_time = tk.Label(info_frame, text="RA", font=("Arial", 12), bg="white")
label_out_time.grid(row=3, column=0, pady=10, sticky="e")
entry_out_time = tk.Entry(info_frame, font=("Arial", 12), width=20)
entry_out_time.grid(row=3, column=1, pady=10, sticky="w")

label_duration = tk.Label(info_frame, text="TỔNG", font=("Arial", 12), bg="white")
label_duration.grid(row=4, column=0, pady=10, sticky="e")
entry_duration = tk.Entry(info_frame, font=("Arial", 12), width=15)
entry_duration.grid(row=4, column=1, pady=10, sticky="w")

label_fee = tk.Label(info_frame, text="TIỀN", font=("Arial", 12), bg="white")
label_fee.grid(row=5, column=0, pady=10, sticky="e")
entry_fee = tk.Entry(info_frame, font=("Arial", 12), width=15)
entry_fee.grid(row=5, column=1, pady=10, sticky="w")

# Khung nút điều khiển
button_frame = tk.Frame(root, bg="white")
button_frame.place(x=750, y=430, width=400, height=160)

# Khung hiển thị thông báo
log_frame = tk.Frame(root, bg="white", highlightbackground="black", highlightthickness=1)
log_frame.place(x=20, y=630, width=1130, height=100)

log_label = tk.Label(log_frame, text="THÔNG BÁO", font=("Arial", 12, "bold"), bg="white")
log_label.pack(anchor="n")

log_text = tk.Text(log_frame, font=("Arial", 12), bg="white", wrap=tk.WORD, state=tk.DISABLED)
log_text.pack(expand=True, fill=tk.BOTH)

# Biến đếm số xe
global vehicle_count  # Khởi tạo biến đếm số xe

def write_log(message):
    """Ghi log vào khung giao diện và in ra terminal."""
    log_text.config(state=tk.NORMAL)  # Cho phép chỉnh sửa Text
    log_text.insert(tk.END, f"{message}\n")  # Thêm thông báo vào Text
    log_text.see(tk.END)  # Cuộn xuống cuối khung Text
    log_text.config(state=tk.DISABLED)  # Khóa Text không cho chỉnh sửa
    print(message)  # In thông báo ra terminal

# Hàm cập nhật thời gian hiện tại lên giao diện
def update_time():
    current_time = datetime.datetime.now().strftime("%H:%M:%S - %d/%m/%Y")  # Lấy thời gian hiện tại
    time_label.config(text=current_time)  # Cập nhật nhãn thời gian
    root.after(1000, update_time)  # Gọi hàm này sau mỗi 1 giây

# Hàm xử lý biển số xe
def process_license_plate(frame):
    plates = yolo_LP_detect(frame, size=640)
    list_plates = plates.pandas().xyxy[0].values.tolist()
    
    if len(list_plates) > 0:
        for plate in list_plates:
            x = int(plate[0])
            y = int(plate[1])
            w = int(plate[2] - plate[0])
            h = int(plate[3] - plate[1])
            crop_img = frame[y:y+h, x:x+w]  # Cắt ảnh biển số
            
            # Nhận diện biển số từ ảnh đã cắt
            lp = helper.read_plate(yolo_license_plate, crop_img)
            if lp != "unknown":
                return lp, crop_img  # Trả về biển số và ảnh cắt
    return "Không thể xác định", None  # Trả về "unknown" và None nếu không nhận diện được

# Hàm xử lý khi ấn nút "VÀO"
def check_in(rfid_tag):
    con = connectDB()
    if con is None:
        return 0  # Trả về 0 nếu không kết nối được đến cơ sở dữ liệu
    
    # Lấy ngày hôm nay
    today = datetime.datetime.now().date()
    
    # Chụp ảnh từ camera vào và nhận diện biển số
    ret, frame = cap_in.read()
    if ret:
        # Nhận diện biển số
        lp, crop_img = process_license_plate(frame)
        
        # Cập nhật biển số vào giao diện
        license_plate_display.config(text=lp)
        
        # Chuyển đổi ảnh từ BGR sang RGB và hiển thị
        if crop_img is not None:
            crop_img_rgb = cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB)
            img_plate_in = Image.fromarray(crop_img_rgb).resize((178, 128))
            img_plate_in = ImageTk.PhotoImage(image=img_plate_in)
            plate_image_display.config(image=img_plate_in)
            plate_image_display.image = img_plate_in

        # Kiểm tra xem xe đã có trong bãi chưa và trạng thái của nó
        status_record = checkNpStatus(rfid_tag)
        
        if status_record is not None:
            # status_record[2] là trường 'status', 1: xe đang trong bãi, 0: xe đã ra khỏi bãi
            if status_record[2] == 1:
                write_log("Xe đã có trong bãi.")
                return
            else:
                # Nếu xe đã ra khỏi bãi trước đó, thêm bản ghi mới để xe vào bãi lại
                insertNp(rfid_tag, lp, crop_img)
                write_log(f"Xe {lp} vào bãi thành công.")
        else:
            # Nếu xe chưa có trong hệ thống, thêm bản ghi mới cho lần đầu vào bãi
            insertNp(rfid_tag, lp, crop_img)
            write_log(f"Xe {lp} vào bãi lần đầu.")
        # Gửi lệnh mở servo xe vào qua ESP32
        try:
            esp32_serial.write(b"OPEN_IN\n")
            write_log("Đã mở lối vào.")
        except serial.SerialException as e:       
            write_log(f"Lỗi khi gửi lệnh mở servo: {e}")
            
    # Câu lệnh SQL để đếm số xe vào trong ngày hôm nay
    query = "SELECT COUNT(*) FROM Numberplate WHERE DATE(date_in) = %s"
    cursor = con.cursor()
    cursor.execute(query, (today,))
    
    # Lấy kết quả
    result = cursor.fetchone()
    
    # Đảm bảo trả về số lượng xe
    vehicle_count = result[0] if result else 0   
    con.close()  # Đóng kết nối sau khi truy vấn xong
    entry_veh_num.delete(0, tk.END)
    entry_veh_num.insert(0, str(vehicle_count))

    # Lấy thời gian hiện tại làm thời gian vào
    in_time = datetime.datetime.now()
    entry_in_time.delete(0, tk.END)
    entry_in_time.insert(0, in_time.strftime("%H:%M:%S - %d/%m/%Y"))
    entry_in_time.in_time = in_time

# Hàm tính phí
def calculate_fee(in_time, out_time):
    # Đảm bảo in_time và out_time là đối tượng datetime
    if not isinstance(in_time, datetime.datetime) or not isinstance(out_time, datetime.datetime):
        raise ValueError("Thời gian vào và ra phải là đối tượng datetime.")
    
    # Tính tổng thời gian đỗ xe (tính bằng giây)
    duration = out_time - in_time
    total_seconds = duration.total_seconds()
    
    # Nếu xe đỗ quá 1 ngày (24 giờ trở lên)
    if total_seconds >= 86400:  # 86400 giây = 24 giờ
        days = total_seconds // 86400  # Tính số ngày (làm tròn xuống)
        return int(days) * 20000  # Phí 20000 VND cho mỗi ngày
    
    # Kiểm tra nếu xe đã đỗ qua đêm (từ 6:00 PM đến 6:00 AM)
    if in_time.hour >= 18 or out_time.hour >= 18:
        # Nếu xe vào trong giờ ban ngày mà đã đỗ qua đêm
        return 10000  # Phí ban đêm 10000 VND, vì đã đỗ qua đêm
    
    # Kiểm tra giờ ra của xe
    if 6 <= out_time.hour < 18:  # Nếu xe ra trong khoảng từ 6 AM - 6 PM (ban ngày)
        return 5000  # Phí 5000 VND nếu xe ra trong khoảng này
    else:  # Nếu xe ra trong khoảng từ 6 PM - 6 AM (ban đêm)
        return 10000  # Phí 10000 VND nếu xe ra trong khoảng này
def check_out(rfid_tag):
    # Kết nối tới cơ sở dữ liệu
    con = connectDB()  # Tạo kết nối cơ sở dữ liệu
    if con is None:
        write_log("Không thể kết nối tới cơ sở dữ liệu")
        return
    
    # Lấy thời gian ra
    out_time = datetime.datetime.now()
    entry_out_time.delete(0, tk.END)
    entry_out_time.insert(0, out_time.strftime("%H:%M:%S - %d/%m/%Y"))

    # Chụp ảnh từ camera ra
    ret, frame = cap_out.read()
    if ret:
        # Nhận diện biển số
        lp, crop_img_out = process_license_plate(frame)  # Gọi hàm nhận diện biển số
        if crop_img_out is None or crop_img_out.size == 0:
            write_log("Ảnh không hợp lệ.")
            return  # Dừng hàm nếu ảnh không hợp lệ
        
        license_plate_display_out.config(text=lp)  # Hiển thị mã biển số ra
        license_plate_display.config(text='')

        # Hiển thị ảnh biển số đã cắt, nếu nhận diện thành công
        if crop_img_out is not None:
            crop_img_out_rgb = cv2.cvtColor(crop_img_out, cv2.COLOR_BGR2RGB)
            img_plate_out = Image.fromarray(crop_img_out_rgb).resize((178, 128))
            img_plate_out = ImageTk.PhotoImage(image=img_plate_out)
            plate_image_display_out.config(image=img_plate_out)
            plate_image_display_out.image = img_plate_out  # Giữ tham chiếu tới ảnh để không bị garbage collected

    # Kiểm tra trong database xem xe đã vào bãi hay chưa
    status_record = checkNpStatus(rfid_tag)
    if status_record and status_record[2] == 1:  # Trạng thái "1" nghĩa là xe đang ở trong bãi
        # Hiển thị ảnh biển số lúc vào (nếu có ảnh từ cơ sở dữ liệu)
        in_plate_image_binary = get_in_plate_image_from_db(con, rfid_tag)  # Hàm lấy ảnh biển số lúc vào từ DB
        if in_plate_image_binary:
            # Chuyển nhị phân sang ảnh và hiển thị
            in_plate_image = convert_binary_to_image(in_plate_image_binary)
            in_plate_image_rgb = cv2.cvtColor(in_plate_image, cv2.COLOR_BGR2RGB)
            img_plate_in = Image.fromarray(in_plate_image_rgb).resize((178, 128))
            img_plate_in = ImageTk.PhotoImage(image=img_plate_in)
            plate_image_display.config(image=img_plate_in)
            plate_image_display.image = img_plate_in  # Giữ tham chiếu tới ảnh

        stored_license_plate = status_record[1]  # Biển số xe từ database

        # So sánh biển số xe đã lưu trong cơ sở dữ liệu với biển số mới nhận diện
        license_plate_display.config(text=stored_license_plate)  # Hiển thị biển số xe từ DB trong giao diện
        if lp != stored_license_plate:
            write_log(f"Cảnh báo: Biển số nhận diện ({lp}) không khớp với biển số trong hệ thống ({stored_license_plate})!")
            return  # Ngừng xử lý nếu biển số không khớp
        
        # Cập nhật thời gian ra và trạng thái trong database
        updateNp(status_record[0], lp, crop_img_out)  # Cập nhật bản ghi bằng ID

        # Hiển thị thời gian vào vào ô nhập
        in_time = status_record[3]  # Thời gian vào từ DB
        entry_in_time.delete(0, tk.END)  # Xóa nội dung cũ trong entry
        entry_in_time.insert(0, in_time.strftime("%H:%M:%S - %d/%m/%Y"))  # Cập nhật thời gian vào

        # Tính thời gian đỗ và phí
        duration = out_time - in_time
        total_seconds = duration.total_seconds()
        entry_duration.delete(0, tk.END)
        entry_duration.insert(0, f"{int(total_seconds)} s")

        # Tính và hiển thị thời gian đỗ xe
        fee = calculate_fee(in_time, out_time)
        entry_fee.delete(0, tk.END)
        entry_fee.insert(0, f"{fee:.0f} VND")

        # Gửi lệnh mở servo xe ra qua ESP32
        try:
            esp32_serial.write(b"OPEN_OUT\n")
            write_log("Đã mở lối ra.")
        except serial.SerialException as e:
            write_log(f"Lỗi khi gửi lệnh mở servo: {e}")
            
        # Hiển thị thông báo
        write_log(f"Xe {lp} đã rời bãi lúc {out_time}")
    else:
        write_log("Xe không có trong bãi hoặc đã rời đi!")

def update_camera():
    # Xử lý video từ camera vào
    ret_in, frame_in = cap_in.read()  # Đọc khung hình từ camera vào
    if ret_in:
        # Chuyển đổi màu từ BGR sang RGB và thay đổi kích thước khung hình
        frame_in_rgb = cv2.cvtColor(frame_in, cv2.COLOR_BGR2RGB)
        frame_in_resized = cv2.resize(frame_in_rgb, (280, 200))
        
        # Phát hiện biển số trên khung hình vào
        plates_in = yolo_LP_detect(frame_in_resized, size=640)
        list_plates_in = plates_in.pandas().xyxy[0].values.tolist()
        
        # Vẽ khung chữ nhật xung quanh biển số nhưng không hiển thị nội dung
        for plate in list_plates_in:
            x, y, w, h = int(plate[0]), int(plate[1]), int(plate[2] - plate[0]), int(plate[3] - plate[1])
            cv2.rectangle(frame_in_resized, (x, y), (x + w, y + h), color=(0, 0, 225), thickness=2)
        
        # Chuyển khung hình thành định dạng ảnh Tkinter và cập nhật trên giao diện
        img_in = ImageTk.PhotoImage(image=Image.fromarray(frame_in_resized))
        camera_in_image.config(image=img_in)
        camera_in_image.image = img_in  # Giữ tham chiếu ảnh để tránh bị xóa

    # Xử lý video từ camera ra (tương tự như trên)
    ret_out, frame_out = cap_out.read()  # Đọc khung hình từ camera ra
    if ret_out:
        frame_out_rgb = cv2.cvtColor(frame_out, cv2.COLOR_BGR2RGB)
        frame_out_resized = cv2.resize(frame_out_rgb, (280, 200))
        
        # Phát hiện biển số trên khung hình ra
        plates_out = yolo_LP_detect(frame_out_resized, size=640)
        list_plates_out = plates_out.pandas().xyxy[0].values.tolist()
        
        # Vẽ khung chữ nhật xung quanh biển số nhưng không hiển thị nội dung
        for plate in list_plates_out:
            x, y, w, h = int(plate[0]), int(plate[1]), int(plate[2] - plate[0]), int(plate[3] - plate[1])
            cv2.rectangle(frame_out_resized, (x, y), (x + w, y + h), color=(0, 0, 225), thickness=2)
        
        # Chuyển khung hình thành định dạng ảnh Tkinter và cập nhật trên giao diện
        img_out = ImageTk.PhotoImage(image=Image.fromarray(frame_out_resized))
        camera_out_image.config(image=img_out)
        camera_out_image.image = img_out  # Giữ tham chiếu ảnh để tránh bị xóa

    # Cập nhật lại khung hình sau mỗi 10 ms
    root.after(10, update_camera)

def show_database_data():
    """Hiển thị dữ liệu trong cơ sở dữ liệu dưới dạng bảng và hỗ trợ xóa, bao gồm hiển thị ảnh."""
    con = connectDB()  # Kết nối tới database
    if con is None:
        write_log("Không thể kết nối tới cơ sở dữ liệu.")
        return

    cursor = con.cursor()
    try:
        # Truy vấn dữ liệu từ bảng Numberplate
        cursor.execute("SELECT id, rfid_tag, number_plate, status, date_in, date_out, in_plate_image, out_plate_image FROM Numberplate")
        rows = cursor.fetchall()

        # Tạo cửa sổ popup để hiển thị dữ liệu
        data_window = tk.Toplevel(root)
        data_window.title("Dữ Liệu Trong Cơ Sở Dữ Liệu")
        data_window.geometry("1200x600")

        # Tạo Frame chính để chứa bảng và nút điều khiển
        data_frame = tk.Frame(data_window)
        data_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tạo Treeview để hiển thị dữ liệu dạng bảng
        tree = ttk.Treeview(
            data_frame,
            columns=("ID", "RFID Tag", "Number Plate", "Status", "Date In", "Date Out"),
            show="headings",
        )
        tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Đặt tiêu đề cho các cột
        tree.heading("ID", text="ID")
        tree.heading("RFID Tag", text="RFID Tag")
        tree.heading("Number Plate", text="Number Plate")
        tree.heading("Status", text="Status")
        tree.heading("Date In", text="Date In")
        tree.heading("Date Out", text="Date Out")

        # Đặt độ rộng cho các cột
        for col in ("ID", "RFID Tag", "Number Plate", "Status", "Date In", "Date Out"):
            tree.column(col, width=150, anchor="center")

        # Thêm dữ liệu vào bảng
        image_data = {}  # Lưu ảnh biển số theo ID
        for row in rows:
            image_data[row[0]] = {"in": row[6], "out": row[7]}  # Lưu dữ liệu nhị phân của ảnh
            tree.insert("", "end", values=row[:6])  # Chỉ thêm dữ liệu văn bản vào bảng

        # Tạo khung chứa các nút điều khiển
        button_frame = tk.Frame(data_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        btn_delete_selected = tk.Button(
            button_frame, text="Xóa Dòng Được Chọn", font=("Arial", 10), bg="red", fg="white", command=lambda: delete_selected(tree, cursor, con)
        )
        btn_delete_selected.pack(side=tk.LEFT, padx=10, pady=5)

        btn_delete_all = tk.Button(
            button_frame, text="Xóa Toàn Bộ Dữ Liệu", font=("Arial", 10), bg="dark red", fg="white", command=lambda: delete_all(tree, cursor, con)
        )
        btn_delete_all.pack(side=tk.RIGHT, padx=10, pady=5)

        # Tạo khung hiển thị ảnh
        image_frame = tk.Frame(data_window, bg="white", highlightbackground="black", highlightthickness=1)
        image_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # Kích thước cố định cho khung ảnh
        image_width, image_height = 200, 150

        # Hiển thị ảnh lúc vào
        in_plate_label = tk.Label(image_frame, text="Ảnh Biển Số Lúc Vào", font=("Arial", 10), bg="white")
        in_plate_label.pack()
        in_plate_display = tk.Canvas(
            image_frame,
            width=image_width,
            height=image_height,
            bg="light gray",
            highlightthickness=1,
            relief=tk.SUNKEN,
        )
        in_plate_display.create_text(
            image_width // 2,
            image_height // 2,
            text="Chưa chọn dòng nào",
            font=("Arial", 10),
            anchor="center",
        )
        in_plate_display.pack(pady=10)

        # Hiển thị ảnh lúc ra
        out_plate_label = tk.Label(image_frame, text="Ảnh Biển Số Lúc Ra", font=("Arial", 10), bg="white")
        out_plate_label.pack()
        out_plate_display = tk.Canvas(
            image_frame,
            width=image_width,
            height=image_height,
            bg="light gray",
            highlightthickness=1,
            relief=tk.SUNKEN,
        )
        out_plate_display.create_text(
            image_width // 2,
            image_height // 2,
            text="Chưa chọn dòng nào",
            font=("Arial", 10),
            anchor="center",
        )
        out_plate_display.pack(pady=10)

        # Hàm cập nhật ảnh hoặc văn bản
        def update_image_display(canvas, image_binary, placeholder_text):
            canvas.delete("all")  # Xóa mọi nội dung trước đó
            if image_binary:
                # Hiển thị ảnh
                image = Image.open(io.BytesIO(image_binary))
                image = image.resize((image_width, image_height))
                image_tk = ImageTk.PhotoImage(image)
                canvas.image = image_tk  # Giữ tham chiếu để tránh bị xóa
                canvas.create_image(0, 0, anchor="nw", image=image_tk)
            else:
                # Hiển thị văn bản khi không có ảnh
                canvas.create_text(
                    image_width // 2,
                    image_height // 2,
                    text=placeholder_text,
                    font=("Arial", 10),
                    anchor="center",
                )

        # Hàm xử lý khi chọn dòng
        def on_select(event):
            selected_item = tree.selection()
            if selected_item:
                record_id = tree.item(selected_item[0])["values"][0]
                if record_id in image_data:
                    # Cập nhật ảnh lúc vào
                    update_image_display(in_plate_display, image_data[record_id]["in"], "Không có ảnh lúc vào")
                    # Cập nhật ảnh lúc ra
                    update_image_display(out_plate_display, image_data[record_id]["out"], "Không có ảnh lúc ra")
            else:
                # Khi chưa chọn dòng nào
                update_image_display(in_plate_display, None, "Chưa chọn dòng nào")
                update_image_display(out_plate_display, None, "Chưa chọn dòng nào")

        tree.bind("<<TreeviewSelect>>", on_select)

        # Hàm xóa dòng dữ liệu được chọn
        def delete_selected(tree, cursor, con):
            try:
                selected_item = tree.selection()
                if not selected_item:
                    write_log("Chưa chọn dòng nào để xóa!")
                    return

                if not con.is_connected():
                    con.reconnect()  # Kết nối lại nếu bị mất

                for item in selected_item:
                    row_data = tree.item(item, "values")
                    if not row_data:
                        write_log("Không lấy được dữ liệu từ dòng được chọn.")
                        continue

                record_id = row_data[0]  # ID của dòng được chọn
                cursor.execute("DELETE FROM Numberplate WHERE id = %s", (record_id,))
                con.commit()

                tree.delete(item)

                write_log("Xóa thành công dữ liệu được chọn.")
            except Exception as e:
                write_log(f"Lỗi khi xóa dữ liệu được chọn: {e}")

        # Hàm xóa toàn bộ dữ liệu
        def delete_all(tree, cursor, con):
            try:
                confirm = tk.messagebox.askyesno("Xác Nhận", "Bạn có chắc chắn muốn xóa tất cả dữ liệu?")
                if not confirm:
                    return

                if not con.is_connected():
                    con.reconnect()  # Kết nối lại nếu bị mất

                cursor.execute("DELETE FROM Numberplate")
                con.commit()

                for item in tree.get_children():
                    tree.delete(item)

                write_log("Xóa toàn bộ dữ liệu thành công.")
            except Exception as e:
                write_log(f"Lỗi khi xóa toàn bộ dữ liệu: {e}")
    except Exception as e:
        print(f"Lỗi xảy ra: {e}")

def open_in_gate():
    """Gửi lệnh mở servo cho lối vào."""
    try:
        esp32_serial.write(b"OPEN_IN\n")  # Gửi lệnh mở cổng vào
        write_log("Đã gửi lệnh mở lối vào.")
    except serial.SerialException as e:
        write_log(f"Lỗi khi gửi lệnh mở servo: {e}")

def open_out_gate():
    """Gửi lệnh mở servo cho lối ra."""
    try:
        esp32_serial.write(b"OPEN_OUT\n")  # Gửi lệnh mở cổng ra
        write_log("Đã gửi lệnh mở lối ra.")
    except serial.SerialException as e:
        write_log(f"Lỗi khi gửi lệnh mở servo: {e}")

def exit_program():
    """ Thoát chương trình và đóng cửa sổ """
    root.destroy()

btn_in = tk.Button(button_frame, text="VÀO", font=("Arial", 12, "bold"), bg="red", fg="white", width=15, command=open_in_gate)
btn_in.grid(row=0, column=0, padx=10, pady=10)

btn_out = tk.Button(button_frame, text="RA", font=("Arial", 12, "bold"), bg="red", fg="white", width=15, command=open_out_gate)
btn_out.grid(row=0, column=1, padx=10, pady=10)

btn_show_data = tk.Button(button_frame, text="Xem Dữ Liệu", font=("Arial", 12, "bold"), bg="blue", fg="white", width=15, command=show_database_data)
btn_show_data.grid(row=1, column=0, padx=10, pady=10)

btn_exit = tk.Button(button_frame, text="THOÁT", font=("Arial", 12, "bold"), bg="gray", fg="white", width=15, command=exit_program)
btn_exit.grid(row=1, column=1, padx=10, pady=10)

update_time()
update_camera()
root.mainloop()
