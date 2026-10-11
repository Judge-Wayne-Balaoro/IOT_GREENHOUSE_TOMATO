Embedded firmware: ESP32-S3, MicroPython, 16x2 I2C LCD

Files to copy to the board:
  main.py, i2c_lcd.py, hcsr04.py
  greenhouse_secrets.py (private: copy greenhouse_secrets.py.example and fill it in)

Wiring:
  LCD SDA -> GPIO 1, SCL -> GPIO 2 (address 0x27 or 0x3F is detected)
  DHT11 -> GPIO 4, HC-SR04 TRIG 5 / ECHO 6, soil ADC GPIO 7, LDR digital GPIO 8
  Relays: pump GPIO 9, fan GPIO 10, grow light GPIO 11

Upload (replace COM7):
  mpremote connect COM7 fs cp main.py :main.py
  mpremote connect COM7 fs cp i2c_lcd.py :i2c_lcd.py
  mpremote connect COM7 fs cp hcsr04.py :hcsr04.py
  mpremote connect COM7 fs cp greenhouse_secrets.py :greenhouse_secrets.py
  mpremote connect COM7 reset

Wi-Fi setup: with no saved network the board starts the hotspot "Greenhouse-Setup"
(password greenhouse123). Join it and open http://192.168.4.1.
To forget the saved network: mpremote connect COM7 fs rm wifi.json
