"""
hardware/motor.py — Stepper motor driver for 28BYJ-48 via ULN2003.

Default GPIO pin mapping (BCM numbering):
    GPIO 2  → IN1
    GPIO 3  → IN2
    GPIO 14 → IN3
    GPIO 22 → IN4

The 28BYJ-48 uses an 8-step half-step sequence for smoother torque.
With the internal ~64:1 gear reduction: 8 steps × 64 = 512 half-steps
per shaft revolution; the full measured value is 4096.

Usage:
    motor = StepperMotor()
    motor.step(200)           # 200 half-steps clockwise
    motor.step(-200)          # 200 half-steps counter-clockwise
    motor.rotate_degrees(90)
    motor.release()           # de-energise coils (prevents overheating)

    # Context manager — cleanup on exit
    with StepperMotor() as m:
        m.rotate_degrees(180)
"""

import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import MotorSettings

# Half-step sequence: columns = IN1, IN2, IN3, IN4
HALF_STEP_SEQUENCE = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
]

STEPS_PER_REVOLUTION = 4096  # half-steps for one full output shaft revolution


class StepperMotor:
    """Driver for a single 28BYJ-48 stepper via ULN2003."""

    def __init__(
        self,
        pin_in1: int   = 2,
        pin_in2: int   = 3,
        pin_in3: int   = 14,
        pin_in4: int   = 22,
        step_delay: float = 0.001,
    ):
        """
        pin_in1..in4 : GPIO BCM pin numbers connected to ULN2003 INx inputs
        step_delay   : seconds between half-steps; minimum stable ~0.001 s
        """
        self._pins       = [pin_in1, pin_in2, pin_in3, pin_in4]
        self._step_delay = step_delay
        self._step_index = 0    # current position in HALF_STEP_SEQUENCE
        self._position   = 0    # accumulated half-steps since start

        import RPi.GPIO as GPIO  # type: ignore
        self._GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in self._pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, n: int) -> None:
        """
        Advance n half-steps.
        n > 0 → clockwise  |  n < 0 → counter-clockwise
        """
        direction = 1 if n >= 0 else -1
        for _ in range(abs(n)):
            self._step_index = (self._step_index + direction) % len(HALF_STEP_SEQUENCE)
            self._apply()
            self._position += direction
            time.sleep(self._step_delay)

    def rotate_degrees(self, degrees: float) -> None:
        """Rotate the output shaft by *degrees* (negative = CCW)."""
        self.step(int(STEPS_PER_REVOLUTION * degrees / 360))

    def rotate_revolutions(self, revolutions: float) -> None:
        """Rotate *revolutions* full turns (may be fractional)."""
        self.step(int(STEPS_PER_REVOLUTION * revolutions))

    def release(self) -> None:
        """De-energise all coils. Call after movement to avoid overheating."""
        for pin in self._pins:
            self._GPIO.output(pin, 0)

    def cleanup(self) -> None:
        """Release coils and free GPIO resources. Call at program exit."""
        self.release()
        self._GPIO.cleanup()

    @property
    def position(self) -> int:
        """Accumulated half-steps since instantiation."""
        return self._position

    @property
    def position_degrees(self) -> float:
        """Accumulated position converted to output-shaft degrees."""
        return self._position * 360 / STEPS_PER_REVOLUTION

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply(self) -> None:
        for pin, val in zip(self._pins, HALF_STEP_SEQUENCE[self._step_index]):
            self._GPIO.output(pin, val)


# ---------------------------------------------------------------------------
# Self-test — python -m src.hardware.motor
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("28BYJ-48 self-test  (GPIO2/3/14/22)")
    with StepperMotor() as m:
        print("→ 1 revolution CW …")
        m.rotate_revolutions(1);  m.release(); time.sleep(0.5)

        print("→ 1 revolution CCW …")
        m.rotate_revolutions(-1); m.release(); time.sleep(0.5)

        print("→ 90° CW …")
        m.rotate_degrees(90);     m.release(); time.sleep(0.5)

        print("→ 90° CCW …")
        m.rotate_degrees(-90);    m.release()

        print(f"Final position: {m.position_degrees:.1f}°")
    print("Done.")
