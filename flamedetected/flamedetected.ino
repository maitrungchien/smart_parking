#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define MQ2_PIN A0
#define FLAME_SENSOR_PIN 2
#define BUZZER_PIN 3
#define FM52_1 4
#define FM52_2 5
#define FM52_3 6
#define FM52_4 7
#define RELAY_PIN 8
#define BUTTON_PIN 13
#define DELAY_RESTART 10000
#define DEBOUNCE_DELAY 50
#define STARTUP_DELAY 2000

unsigned long previousMillis = 0;
unsigned long lastDebounceTime = 0;
unsigned long startupTime = 0;
bool relayOff = false;
bool fireDetected = false;
bool buttonPressedLast = false;
bool buttonPressedForRestart = false;
bool systemReady = false;

LiquidCrystal_I2C lcd(0x27, 16, 2);

void setup() {
  Serial.begin(9600);
  pinMode(FLAME_SENSOR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  
  digitalWrite(RELAY_PIN, HIGH); // Bật relay ban đầu
  
  for (int i = FM52_1; i <= FM52_4; i++) {
    pinMode(i, INPUT);
  }

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Starting...");
  
  startupTime = millis();
  while (millis() - startupTime < STARTUP_DELAY) {
    delay(100);
  }
  systemReady = true;
  lcd.clear();
}

void loop() {
  int mq2_value = analogRead(MQ2_PIN);
  int flame_detected = digitalRead(FLAME_SENSOR_PIN);
  int buttonState = digitalRead(BUTTON_PIN);
  unsigned long currentMillis = millis();
  
  String data = "FLAME:" + String(flame_detected == LOW ? 0 : 1) + ",MQ2:" + String(mq2_value);
  Serial.println(data);
  
  if (systemReady) {
    // Debug trạng thái nút
    Serial.print("Button state: ");
    Serial.println(buttonState);

    // Xử lý nút nhấn với debouncing đơn giản
    if (currentMillis - lastDebounceTime > DEBOUNCE_DELAY) {
      if (buttonState == LOW && !buttonPressedLast) {
        Serial.println("Button pressed detected!");
        if (!relayOff) {
          Serial.println("Da tat nguon thu cong");
          digitalWrite(RELAY_PIN, LOW);
          relayOff = true;
          fireDetected = false;
        } else if (!fireDetected) {
          Serial.println("Da bat nguon thu cong");
          digitalWrite(RELAY_PIN, HIGH);
          relayOff = false;
        } else if (fireDetected) {
          buttonPressedForRestart = true;
          Serial.println("Waiting to restart after fire...");
        }
        buttonPressedLast = true;
        lastDebounceTime = currentMillis; // Cập nhật thời gian debounce
      } else if (buttonState == HIGH) {
        buttonPressedLast = false;
      }
    }

    // Kiểm tra cảm biến
    if (mq2_value > 300 || flame_detected == LOW) {
      digitalWrite(BUZZER_PIN, HIGH);
      if (!relayOff) {
        Serial.println("OPEN_OUT");
        delay(500);
        digitalWrite(RELAY_PIN, LOW);
        previousMillis = currentMillis;
        relayOff = true;
        fireDetected = true;
        buttonPressedForRestart = false;
      }
    } else {
      digitalWrite(BUZZER_PIN, LOW);
      if (relayOff && fireDetected && currentMillis - previousMillis >= DELAY_RESTART) {
        if (buttonPressedForRestart && mq2_value <= 300 && flame_detected == HIGH) {
          digitalWrite(RELAY_PIN, HIGH);
          Serial.println("ESP32 started!");
          Serial.println("CLOSE_OUT");
          relayOff = false;
          fireDetected = false;
          buttonPressedForRestart = false;
        }
      }
    }
  }

  // Hiển thị lên LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("1  2  3  4  Gas");
  lcd.setCursor(0, 1);
  int fm_values[4];
  fm_values[0] = digitalRead(FM52_1);
  fm_values[1] = digitalRead(FM52_2);
  fm_values[2] = digitalRead(FM52_3);
  fm_values[3] = digitalRead(FM52_4);
  for (int i = 0; i < 4; i++) {
    lcd.print(fm_values[i] == LOW ? "X  " : "O  ");
  }
  lcd.setCursor(12, 1);
  lcd.print(mq2_value);

  if (systemReady && relayOff && fireDetected && currentMillis - previousMillis < DELAY_RESTART) {
    lcd.setCursor(0, 1);
    lcd.print("Wait ");
    lcd.print((DELAY_RESTART - (currentMillis - previousMillis)) / 1000);
    lcd.print("s    ");
  }

  delay(500);
}