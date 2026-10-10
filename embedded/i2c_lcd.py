"""Minimal MicroPython driver for a 16x2 HD44780 character LCD with a PCF8574 I2C backpack.

Common backpack mapping: P0=RS, P1=RW, P2=E, P3=backlight, P4..P7=D4..D7.
If the backpack uses a different mapping, this driver may need adjustment.
"""
import time


class I2cLcd:
    RS = 0x01
    RW = 0x02
    EN = 0x04
    BACKLIGHT = 0x08

    LCD_CLEAR = 0x01
    LCD_HOME = 0x02
    LCD_ENTRY_MODE = 0x04
    LCD_ENTRY_LEFT = 0x02
    LCD_DISPLAY_CONTROL = 0x08
    LCD_DISPLAY_ON = 0x04
    LCD_FUNCTION_SET = 0x20
    LCD_2_LINE = 0x08
    LCD_5x8_DOTS = 0x00
    LCD_SET_DDRAM = 0x80

    ROW_OFFSETS = (0x00, 0x40, 0x14, 0x54)

    def __init__(self, i2c, addr=0x27, num_lines=2, num_columns=16):
        if num_lines not in (1, 2, 4):
            raise ValueError("num_lines should be 1, 2, or 4")
        self.i2c = i2c
        self.addr = addr
        self.num_lines = num_lines
        self.num_columns = num_columns
        self.backlight_enabled = True
        self._backlight_bit = self.BACKLIGHT
        self._init_lcd()

    def _write_expander(self, value):
        if self.backlight_enabled:
            value |= self._backlight_bit
        else:
            value &= ~self._backlight_bit
        self.i2c.writeto(self.addr, bytes((value & 0xFF,)))

    def _pulse_enable(self, value):
        self._write_expander(value | self.EN)
        time.sleep_us(1)
        self._write_expander(value & ~self.EN)
        time.sleep_us(50)

    def _write4(self, nibble, mode=0):
        # nibble contains data in bits 7..4; mode is RS for data or 0 for command.
        value = (nibble & 0xF0) | mode
        self._pulse_enable(value)

    def _send(self, value, mode=0):
        self._write4(value & 0xF0, mode)
        self._write4((value << 4) & 0xF0, mode)

    def _command(self, command):
        self._send(command, 0)
        if command in (self.LCD_CLEAR, self.LCD_HOME):
            time.sleep_ms(2)

    def _init_lcd(self):
        time.sleep_ms(50)
        # Reset into 4-bit mode per HD44780 initialization sequence.
        self._write4(0x30)
        time.sleep_ms(5)
        self._write4(0x30)
        time.sleep_us(150)
        self._write4(0x30)
        self._write4(0x20)

        function = self.LCD_FUNCTION_SET | self.LCD_2_LINE | self.LCD_5x8_DOTS
        self._command(function)
        self._command(self.LCD_DISPLAY_CONTROL | self.LCD_DISPLAY_ON)
        self._command(self.LCD_CLEAR)
        self._command(self.LCD_ENTRY_MODE | self.LCD_ENTRY_LEFT)
        time.sleep_ms(2)

    def clear(self):
        self._command(self.LCD_CLEAR)

    def home(self):
        self._command(self.LCD_HOME)

    def move_to(self, column, row):
        if not 0 <= column < self.num_columns:
            raise ValueError("column outside LCD dimensions")
        if not 0 <= row < self.num_lines:
            raise ValueError("row outside LCD dimensions")
        self._command(self.LCD_SET_DDRAM | (self.ROW_OFFSETS[row] + column))

    def putchar(self, char):
        if char == "\n":
            return
        self._send(ord(char), self.RS)

    def putstr(self, text):
        for char in str(text):
            if char == "\n":
                # Convenience: newline moves to the next LCD row, column zero.
                # Keep line number within the configured display height.
                self._newline()
            else:
                self.putchar(char)

    def _newline(self):
        current = getattr(self, "_text_row", 0) + 1
        if current >= self.num_lines:
            current = 0
        self._text_row = current
        self.move_to(0, current)

    def set_backlight(self, enabled):
        self.backlight_enabled = bool(enabled)
        self._write_expander(0)

    def display_on(self, enabled=True):
        self._command(self.LCD_DISPLAY_CONTROL | (self.LCD_DISPLAY_ON if enabled else 0))
