import machine
import time


class HCSR04:
    def __init__(self, trigger_pin, echo_pin, echo_timeout_us=50000):
        self.echo_timeout_us = echo_timeout_us
        self.trigger = machine.Pin(trigger_pin, machine.Pin.OUT)
        self.echo = machine.Pin(echo_pin, machine.Pin.IN)

        self.trigger.value(0)

    def _send_pulse_and_wait(self):
        self.trigger.value(0)
        time.sleep_us(2)

        self.trigger.value(1)
        time.sleep_us(10)

        self.trigger.value(0)

        try:
            pulse_time = machine.time_pulse_us(
                self.echo,
                1,
                self.echo_timeout_us
            )
        except OSError:
            pulse_time = -1

        return pulse_time

    def distance_mm(self):
        pulse_time = self._send_pulse_and_wait()

        if pulse_time < 0:
            raise OSError("Ultrasonic timeout")

        # Speed of sound ≈ 0.343 mm/us
        # Divide by 2 because sound travels to object and back
        distance = pulse_time * 0.343 / 2

        return distance

    def distance_cm(self):
        return self.distance_mm() / 10