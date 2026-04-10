"""
tests/test_motor.py — Unit tests for src/hardware/motor.py

These tests run WITHOUT a Raspberry Pi.  A lightweight GPIO mock is
injected so no real hardware is touched.  Every logical behaviour of
StepperMotor and DualStepperMotor is covered independently.

Run with:
    python -m pytest tests/test_motor.py -v
    # or without pytest:
    python tests/test_motor.py
"""

import sys
import os
import types
import unittest
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Make the project root importable regardless of working directory
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# GPIO mock — replaces RPi.GPIO before motor.py imports it
# ---------------------------------------------------------------------------

def _make_gpio_mock():
    """Return a MagicMock that behaves like RPi.GPIO (BCM constants, etc.)."""
    gpio = MagicMock()
    gpio.BCM   = 11   # real value doesn't matter for logic tests
    gpio.OUT   = 0
    gpio.HIGH  = 1
    gpio.LOW   = 0
    return gpio


def _load_motor_with_mock_gpio():
    """
    Import motor.py with RPi.GPIO replaced by a fresh mock.
    Returns (module, gpio_mock).
    """
    gpio_mock = _make_gpio_mock()

    # Build a fake 'RPi' package so `import RPi.GPIO` succeeds
    rpi_pkg  = types.ModuleType("RPi")
    rpi_pkg.GPIO = gpio_mock
    sys.modules["RPi"]      = rpi_pkg
    sys.modules["RPi.GPIO"] = gpio_mock

    # Force re-import if module was already loaded
    for key in list(sys.modules):
        if "motor" in key and "hardware" in key:
            del sys.modules[key]

    from src.hardware.motor import StepperMotor, DualStepperMotor
    return StepperMotor, DualStepperMotor, gpio_mock


StepperMotor, DualStepperMotor, _GPIO = _load_motor_with_mock_gpio()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_motor(dir_pin=26, step_pin=19, step_delay=0, steps_per_rev=200):
    """Create a StepperMotor with zero delay (fast tests) and fresh mock."""
    gpio = _make_gpio_mock()
    rpi_pkg = types.ModuleType("RPi")
    rpi_pkg.GPIO = gpio
    sys.modules["RPi"]      = rpi_pkg
    sys.modules["RPi.GPIO"] = gpio

    m = StepperMotor(
        dir_pin=dir_pin,
        step_pin=step_pin,
        step_delay=step_delay,
        steps_per_rev=steps_per_rev,
    )
    m._GPIO = gpio   # expose the mock for assertion
    return m, gpio


# ===========================================================================
# StepperMotor tests
# ===========================================================================

class TestStepperMotorInit(unittest.TestCase):
    """GPIO setup is called correctly on construction."""

    def test_pins_configured_as_output(self):
        m, gpio = make_motor(dir_pin=26, step_pin=19)
        gpio.setup.assert_any_call(26, gpio.OUT)
        gpio.setup.assert_any_call(19, gpio.OUT)

    def test_pins_initialised_low(self):
        m, gpio = make_motor(dir_pin=26, step_pin=19)
        gpio.output.assert_any_call(26, 0)
        gpio.output.assert_any_call(19, 0)

    def test_initial_position_zero(self):
        m, _ = make_motor()
        self.assertEqual(m.position, 0)

    def test_initial_position_degrees_zero(self):
        m, _ = make_motor()
        self.assertAlmostEqual(m.position_degrees, 0.0)


class TestStepperMotorStep(unittest.TestCase):
    """step(n) drives the STEP pin and tracks position."""

    def test_step_zero_does_nothing(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        m.step(0)
        gpio.output.assert_not_called()
        self.assertEqual(m.position, 0)

    def test_positive_steps_set_dir_high(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        m.step(5)
        # First output call after reset should set DIR HIGH
        dir_calls = [c for c in gpio.output.call_args_list if c.args[0] == m._dir_pin]
        self.assertTrue(any(c.args[1] == gpio.HIGH for c in dir_calls))

    def test_negative_steps_set_dir_low(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        m.step(-5)
        dir_calls = [c for c in gpio.output.call_args_list if c.args[0] == m._dir_pin]
        self.assertTrue(any(c.args[1] == gpio.LOW for c in dir_calls))

    def test_step_count_positive(self):
        m, gpio = make_motor()
        m.step(10)
        self.assertEqual(m.position, 10)

    def test_step_count_negative(self):
        m, gpio = make_motor()
        m.step(-7)
        self.assertEqual(m.position, -7)

    def test_step_accumulates(self):
        m, _ = make_motor()
        m.step(10)
        m.step(-3)
        self.assertEqual(m.position, 7)

    def test_step_pin_toggled_once_per_step(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        n = 6
        m.step(n)
        high_pulses = [
            c for c in gpio.output.call_args_list
            if c.args[0] == m._step_pin and c.args[1] == gpio.HIGH
        ]
        self.assertEqual(len(high_pulses), n)


class TestStepperMotorRotate(unittest.TestCase):
    """rotate_degrees and rotate_revolutions calculate steps correctly."""

    def test_rotate_full_revolution(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_revolutions(1)
        self.assertEqual(m.position, 200)

    def test_rotate_negative_revolution(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_revolutions(-1)
        self.assertEqual(m.position, -200)

    def test_rotate_90_degrees(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_degrees(90)
        self.assertEqual(m.position, 50)   # 200 * 90/360

    def test_rotate_180_degrees(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_degrees(180)
        self.assertEqual(m.position, 100)

    def test_rotate_negative_degrees(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_degrees(-90)
        self.assertEqual(m.position, -50)

    def test_position_degrees_roundtrip(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_degrees(45)
        self.assertAlmostEqual(m.position_degrees, 45.0, places=1)

    def test_fractional_revolution(self):
        m, _ = make_motor(steps_per_rev=200)
        m.rotate_revolutions(0.5)
        self.assertEqual(m.position, 100)


class TestStepperMotorRelease(unittest.TestCase):
    """release() is a no-op for STEP/DIR (coils managed by driver board)."""

    def test_release_does_not_raise(self):
        m, _ = make_motor()
        m.release()   # should not raise

    def test_release_does_not_change_position(self):
        m, _ = make_motor()
        m.step(5)
        m.release()
        self.assertEqual(m.position, 5)


class TestStepperMotorCleanup(unittest.TestCase):
    """cleanup() sets pins low and calls GPIO.cleanup()."""

    def test_cleanup_sets_pins_low(self):
        m, gpio = make_motor(dir_pin=26, step_pin=19)
        gpio.reset_mock()
        m.cleanup()
        gpio.output.assert_any_call(26, 0)
        gpio.output.assert_any_call(19, 0)

    def test_cleanup_calls_gpio_cleanup(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        m.cleanup()
        gpio.cleanup.assert_called_once()


class TestStepperMotorContextManager(unittest.TestCase):
    """Context manager calls cleanup() on exit."""

    def test_context_manager_calls_cleanup(self):
        m, gpio = make_motor()
        gpio.reset_mock()
        with m:
            m.step(3)
        gpio.cleanup.assert_called_once()

    def test_context_manager_returns_motor(self):
        m, _ = make_motor()
        with m as ctx:
            self.assertIs(ctx, m)


# ===========================================================================
# DualStepperMotor tests
# ===========================================================================

class TestDualStepperMotor(unittest.TestCase):
    """DualStepperMotor wires up two independent StepperMotor instances."""

    def _make_dual(self):
        """Create a DualStepperMotor with both sub-motors using zero delay."""
        # We patch StepperMotor.__init__ to avoid real GPIO; instead we let
        # each StepperMotor use the mock already in sys.modules.
        gpio = _make_gpio_mock()
        rpi_pkg = types.ModuleType("RPi")
        rpi_pkg.GPIO = gpio
        sys.modules["RPi"]      = rpi_pkg
        sys.modules["RPi.GPIO"] = gpio

        dual = DualStepperMotor(
            az_dir=26, az_step=19,
            el_dir=21, el_step=20,
            step_delay=0,
        )
        dual.azimuth._GPIO   = gpio
        dual.elevation._GPIO = gpio
        return dual, gpio

    def test_azimuth_and_elevation_are_separate_instances(self):
        dual, _ = self._make_dual()
        self.assertIsNot(dual.azimuth, dual.elevation)

    def test_azimuth_pins(self):
        dual, _ = self._make_dual()
        self.assertEqual(dual.azimuth._dir_pin,  26)
        self.assertEqual(dual.azimuth._step_pin, 19)

    def test_elevation_pins(self):
        dual, _ = self._make_dual()
        self.assertEqual(dual.elevation._dir_pin,  21)
        self.assertEqual(dual.elevation._step_pin, 20)

    def test_independent_positions(self):
        dual, _ = self._make_dual()
        dual.azimuth.step(10)
        dual.elevation.step(5)
        self.assertEqual(dual.azimuth.position,   10)
        self.assertEqual(dual.elevation.position,  5)

    def test_context_manager_cleanup(self):
        dual, gpio = self._make_dual()
        with dual:
            dual.azimuth.step(3)
        gpio.cleanup.assert_called_once()

    def test_release_does_not_raise(self):
        dual, _ = self._make_dual()
        dual.release()


# ===========================================================================
# Edge-case / regression tests
# ===========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_large_step_count(self):
        """3200 steps (1/16 microstepping, 1 rev) should not raise."""
        m, _ = make_motor(steps_per_rev=3200)
        m.rotate_revolutions(1)
        self.assertEqual(m.position, 3200)

    def test_direction_reversal_mid_sequence(self):
        m, _ = make_motor()
        m.step(50)
        m.step(-50)
        self.assertEqual(m.position, 0)

    def test_many_small_steps_accumulate(self):
        m, _ = make_motor()
        for _ in range(10):
            m.step(1)
        self.assertEqual(m.position, 10)

    def test_custom_steps_per_rev(self):
        m, _ = make_motor(steps_per_rev=400)  # half-step
        m.rotate_degrees(180)
        self.assertEqual(m.position, 200)   # 400 * 180/360


# ===========================================================================
# Runner for python tests/test_motor.py (no pytest required)
# ===========================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
