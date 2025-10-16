#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>

// Định nghĩa chân cho module RFID
#define SS_PIN_1 5   // Chân SS cho module RFID 1 (xe vào)
#define RST_PIN_1 22 // Chân RST cho module RFID 1
#define SS_PIN_2 4   // Chân SS cho module RFID 2 (xe ra)
#define RST_PIN_2 21 // Chân RST cho module RFID 2

// Định nghĩa chân cho cảm biến hồng ngoại
#define PIN_IR_IN 15  // Cảm biến hồng ngoại xe vào
#define PIN_IR_OUT 13 // Cảm biến hồng ngoại xe ra

// Định nghĩa chân cho servo
#define PIN_SERVO_IN 14  // Servo xe vào
#define PIN_SERVO_OUT 27 // Servo xe ra

#define RX2 16  // GPIO16 - Nhận dữ liệu từ Arduino

// Khởi tạo module RFID
MFRC522 rfid_in(SS_PIN_1, RST_PIN_1);  // RFID cho xe vào
MFRC522 rfid_out(SS_PIN_2, RST_PIN_2); // RFID cho xe ra

// Khởi tạo servo
Servo servo_in;  // Servo xe vào
Servo servo_out; // Servo xe ra

void setup() {
  Serial.begin(115200); // Đặt tốc độ baud
  Serial2.begin(9600);  // Nhận dữ liệu từ Arduino (TX2: GPIO17, RX2: GPIO16)
  SPI.begin();          // Khởi tạo giao tiếp SPI

  // Khởi tạo module RFID
  rfid_in.PCD_Init();
  rfid_out.PCD_Init();

  // Khởi tạo cảm biến hồng ngoại
  pinMode(PIN_IR_IN, INPUT);
  pinMode(PIN_IR_OUT, INPUT);

  // Khởi tạo servo
  servo_in.attach(PIN_SERVO_IN);
  servo_out.attach(PIN_SERVO_OUT);

  // Đặt trạng thái ban đầu của servo
  servo_in.write(90);  // Đóng servo xe vào
  servo_out.write(90); // Đóng servo xe ra

  Serial.println("READY"); // Thông báo sẵn sàng
}

void loop() {
  // Nhận dữ liệu từ Arduino qua Serial2
  if (Serial2.available() > 0) {
    String data = Serial2.readStringUntil('\n');
    data.trim();
    // Xử lý lệnh mở servo_out
    if (data == "OPEN_OUT") {
      Serial.println("Mở servo xe ra do cháy.");
      servo_out.write(0); // Mở servo ra
      Serial.println("SERVO_OUT_OPEN");
    }
    // Xử lý lệnh đóng servo_out
    else if (data == "CLOSE_OUT") {
      Serial.println("Đóng servo xe ra từ Arduino.");
      servo_out.write(90); // Đóng servo ra
      Serial.println("SERVO_OUT_CLOSED");
    } 
    // Phân tích dữ liệu
    int flameIndex = data.indexOf("FLAME:");
    int mq2Index = data.indexOf(",MQ2:");
    
    if (flameIndex != -1 && mq2Index != -1) {
      String flameStr = data.substring(flameIndex + 6, mq2Index);
      String mq2Str = data.substring(mq2Index + 5);
      
      int flameValue = flameStr.toInt();
      int mq2Value = mq2Str.toInt();

      // In dữ liệu nhận được để debug
      Serial.print("Flame: ");
      Serial.print(flameValue);
      Serial.print(", MQ2: ");
      Serial.println(mq2Value);
    }
  }

    // Đọc trạng thái cảm biến hồng ngoại
    bool ir_in_triggered = digitalRead(PIN_IR_IN);
    bool ir_out_triggered = digitalRead(PIN_IR_OUT);

    // Xử lý lệnh từ Serial
    if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n');
        command.trim(); // Xóa khoảng trắng

        if (command == "RESET") {
            Serial.println("Đang reset ESP32...");
            ESP.restart(); // Reset lại ESP32
        } else if (command == "OPEN_IN") {
            Serial.println("Mở servo xe vào.");
            servo_in.write(0); // Mở servo xe vào
            delay(200);        // Giữ trạng thái
            Serial.println("SERVO_IN_OPEN"); // Gửi trạng thái mở
        } else if (command == "OPEN_OUT") {
            Serial.println("Mở servo xe ra.");
            servo_out.write(0); // Mở servo xe ra
            delay(200);         // Giữ trạng thái
            Serial.println("SERVO_OUT_OPEN"); // Gửi trạng thái mở
        }
    }

    // Đóng servo khi cảm biến xe vào kích hoạt
    if (digitalRead(PIN_IR_IN) == LOW) {
        Serial.println("Cảm biến xe vào kích hoạt. Đóng servo.");
        servo_in.write(90); // Đóng servo
        delay(500);         // Tránh lặp liên tục
        Serial.println("SERVO_IN_CLOSED"); // Gửi trạng thái đóng
    }

    // Đóng servo khi cảm biến xe ra kích hoạt
    if (digitalRead(PIN_IR_OUT) == LOW) {
        Serial.println("Cảm biến xe ra kích hoạt. Đóng servo.");
        servo_out.write(90); // Đóng servo
        delay(500);          // Tránh lặp liên tục
        Serial.println("SERVO_OUT_CLOSED"); // Gửi trạng thái đóng
    }

    // Xử lý RFID cho xe vào
    if (rfid_in.PICC_IsNewCardPresent() && rfid_in.PICC_ReadCardSerial()) {
        String rfidTag = "";
        for (byte i = 0; i < rfid_in.uid.size; i++) {
            rfidTag += String(rfid_in.uid.uidByte[i], HEX);  // Lấy mã thẻ RFID
        }
        Serial.println("IN," + rfidTag); // Gửi tín hiệu qua Serial

        // Mở servo cho xe vào
        servo_in.write(0); // Giả sử 0 độ là mở
        delay(2000);       // Giữ cửa mở 2 giây
    }

    // Xử lý RFID cho xe ra
    if (rfid_out.PICC_IsNewCardPresent() && rfid_out.PICC_ReadCardSerial()) {
        String rfidTag = "";
        for (byte i = 0; i < rfid_out.uid.size; i++) {
            rfidTag += String(rfid_out.uid.uidByte[i], HEX);  // Lấy mã thẻ RFID
        }
        Serial.println("OUT," + rfidTag); // Gửi tín hiệu qua Serial

        // Mở servo cho xe ra
        servo_out.write(0); // Giả sử 0 độ là mở
        delay(2000);        // Giữ cửa mở 2 giây
    }
}
