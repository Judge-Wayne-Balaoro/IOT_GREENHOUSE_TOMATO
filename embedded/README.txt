OLED standard driver test (ESP32-S3, 0.96-inch I2C 128x64)

Wiring assumed:
VCC -> 3V3
GND -> GND
SDA -> GPIO 12
SCK/SCL -> GPIO 13
I2C address -> 0x3C

1) Back up your current ssd1306.py and oled_test.py.
2) Copy these two files into C:\Users\Saibankan\Desktop\IOT\embedded, replacing the existing copies.
3) Upload them to the ESP32:
   mpremote connect COM7 fs cp .\ssd1306.py :ssd1306.py
   mpremote connect COM7 fs cp .\oled_test.py :oled_test.py
4) Run:
   mpremote connect COM7 run .\oled_test.py

Expected: white full-screen for 3 seconds, then text. This uses a standard SSD1306 init sequence and should also work with many SSD1315-compatible displays.
If I2C scan returns 0x3C but the panel is still fully blank after this test, do not assume it is definitely defective yet; verify the exact module/pin mode and try the display on a known-good controller if possible.
