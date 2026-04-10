"""
hardware/motor.py — Dual stepper motor driver using STEP/DIR interface
                    (compatible with A4988, DRV8825, or similar drivers).

GPIO pin mapping (BCM numbering):
    Motor 0 (Azimuth):
        GPIO 26 → DIR
        GPIO 19 → STEP

    Motor 1 (Elevation):
        GPIO 21 → DIR
        GPIO 20 → STEP

The step resolution (full/half/micro) is set by the MS pins on the driver
board — not in software.  This driver assumes you have configured the
hardware for the desired resolution before running.

Steps per revolution depends on your motor (usually 200 for 1.8° motors)
multiplied by the microstepping factor set on the driver.

Usage:
    az  = StepperMotor(dir_pin=26, step_pin=19)
    el  = StepperMotor(dir_pin=21, step_pin=20)
    az.step(200)              # 200 steps clockwise
    az.step(-200)             # 200 steps counter-clockwise
    el.rotate_degrees(90)
    az.release()              # no-op for STEP/DIR (coils managed by driver)

    # Context manager — cleanup on exit
    with StepperMotor(dir_pin=26, step_pin=19) as m:
        m.rotate_degrees(180)

    # Both axes together
    with DualStepperMotor() as mount:
        mount.azimuth.rotate_degrees(45)
        mount.elevation.rotate_degrees(15)
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Steps for one full revolution.
# Adjust for your motor (200 = 1.8° full-step, 400 = 0.9°, etc.)
# Multiply by microstepping factor if MS pins are set (e.g. 200 × 16 = 3200).
STEPS_PER_REVOLUTION = 200

# Minimum pulse width for STEP pin (seconds).
# A4988 requires ≥ 1 µs; DRV8825 requires ≥ 1.9 µs.  1 µs is safe for both.
_STEP_PULSE_WIDTH = 0.000002   # 2 µs


class StepperMotor:
    """
    Driver for a single stepper motor connected via a STEP/DIR driver board
    (A4988, DRV8825, TMC2208, etc.).
    """

    def __init__(
        self,
        dir_pin: int = 26,
        step_pin: int = 19,
        step_delay: float = 0.0005,
        steps_per_rev: int = STEPS_PER_REVOLUTION,
    ):
        """
        dir_pin       : BCM GPIO pin connected to the driver DIR input
        step_pin      : BCM GPIO pin connected to the driver STEP input
        step_delay    : seconds between steps (controls speed)
        steps_per_rev : steps for one full output shaft revolution
        """
        self._dir_pin       = dir_pin
        self._step_pin      = step_pin
        self._step_delay    = step_delay
        self._steps_per_rev = steps_per_rev
        self._position      = 0   # accumulated steps since start

        import RPi.GPIO as GPIO   # type: ignore
        self._GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._dir_pin,  GPIO.OUT)
        GPIO.setup(self._step_pin, GPIO.OUT)
        GPIO.output(self._dir_pin,  0)
        GPIO.output(self._step_pin, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, n: int) -> None:
        """
        Advance n steps.
        n > 0 → clockwise (DIR HIGH)
        n < 0 → counter-clockwise (DIR LOW)
        """
        if n == 0:
            return

        direction = 1 if n > 0 else -1
        self._GPIO.output(self._dir_pin, GPIO.HIGH if direction > 0 else GPIO.LOW)

        # Small settle time after direction change
        time.sleep(_STEP_PULSE_WIDTH)

        for _ in range(abs(n)):
            self._GPIO.output(self._step_pin, self._GPIO.HIGH)
            time.sleep(_STEP_PULSE_WIDTH)
            self._GPIO.output(self._step_pin, self._GPIO.LOW)
            time.sleep(self._step_delay)
            self._position += direction

    def rotate_degrees(self, degrees: float) -> None:
        """Rotate the output shaft by *degrees* (negative = CCW)."""
        self.step(round(self._steps_per_rev * degrees / 360))

    def rotate_revolutions(self, revolutions: float) -> None:
        """Rotate *revolutions* full turns (may be fractional)."""
        self.step(round(self._steps_per_rev * revolutions))

    def release(self) -> None:
        """
        No-op for STEP/DIR drivers — coil current is managed by the driver
        board (enable pin).  Included for API compatibility with the previous
        ULN2003 driver.
        """
        pass

    def cleanup(self) -> None:
        """Set pins low and free GPIO resources.  Call at program exit."""
        self._GPIO.output(self._dir_pin,  0)
        self._GPIO.output(self._step_pin, 0)
        self._GPIO.cleanup()

    @property
    def position(self) -> int:
        """Accumulated steps since instantiation."""
        return self._position

    @property
    def position_degrees(self) -> float:
        """Accumulated position converted to output-shaft degrees."""
        return self._position * 360 / self._steps_per_rev

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
        """Legacy stub — not used by STEP/DIR interface."""
        pass


# ---------------------------------------------------------------------------
# Convenience wrapper for the two-axis telescope mount
# ---------------------------------------------------------------------------

class DualStepperMotor:
    """
    Manages both azimuth and elevation axes.

    Default wiring:
        Azimuth   : DIR=GPIO26, STEP=GPIO19
        Elevation : DIR=GPIO21, STEP=GPIO20
    """

    def __init__(
        self,
        az_dir: int   = 26,
        az_step: int  = 19,
        el_dir: int   = 21,
        el_step: int  = 20,
        step_delay: float = 0.0005,
    ):
        self.azimuth   = StepperMotor(dir_pin=az_dir,  step_pin=az_step,  step_delay=step_delay)
        self.elevation = StepperMotor(dir_pin=el_dir,  step_pin=el_step,  step_delay=step_delay)

    def release(self) -> None:
        self.azimuth.release()
        self.elevation.release()

    def cleanup(self) -> None:
        # Only call GPIO.cleanup() once
        self.azimuth._GPIO.output(self.azimuth._dir_pin,  0)
        self.azimuth._GPIO.output(self.azimuth._step_pin, 0)
        self.elevation._GPIO.output(self.elevation._dir_pin,  0)
        self.elevation._GPIO.output(self.elevation._step_pin, 0)
        self.azimuth._GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()


# ---------------------------------------------------------------------------
# Self-test — python -m src.hardware.motor
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("STEP/DIR dual-motor self-test")
    print("  Azimuth  : DIR=GPIO26  STEP=GPIO19")
    print("  Elevation: DIR=GPIO21  STEP=GPIO20")

    with DualStepperMotor() as mount:
        print("\n[AZ]  → 1 revolution CW …")
        mount.azimuth.rotate_revolutions(1)
        time.sleep(0.3)

        print("[AZ]  → 1 revolution CCW …")
        mount.azimuth.rotate_revolutions(-1)
        time.sleep(0.3)

        print("[EL]  → 90° CW …")
        mount.elevation.rotate_degrees(90)
        time.sleep(0.3)

        print("[EL]  → 90° CCW …")
        mount.elevation.rotate_degrees(-90)
        time.sleep(0.3)

        print(f"\nFinal positions — AZ: {mount.azimuth.position_degrees:.1f}°"
              f"  EL: {mount.elevation.position_degrees:.1f}°")

    print("Done.")
