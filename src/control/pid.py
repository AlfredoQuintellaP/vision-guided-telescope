"""
control/pid.py — PID controller for a single telescope axis.

Features:
  - Output clamping         : correction stays within ±max_output
  - Integral windup guard   : integral stops accumulating when output is saturated
  - Derivative on measurement: avoids derivative kick on setpoint changes
  - reset()                 : clears internal state on detection loss

Error convention:
    error  = detected_moon_position − image_centre   (pixels, or normalised –1…1)
    positive error → moon is right / below centre → motor must move right / down
"""

import time

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import PIDSettings


class PID:
    """
    Discrete PID controller.

    Typical use:
        pid = PID()                 # uses CFG.pid defaults
        pid = PID(PIDSettings(...)) # custom settings

        correction = pid.update(error_pixels, dt_seconds)
    """

    def __init__(self, settings: PIDSettings | None = None):
        if settings is None:
            from config import CFG
            settings = CFG.pid
        s = settings
        self.kp             = s.kp
        self.ki             = s.ki
        self.kd             = s.kd
        self.max_output     = s.max_output
        self.integral_limit = s.integral_limit
        self.deadband       = s.deadband

        self._integral:          float       = 0.0
        self._last_measurement:  float|None  = None
        self._last_time:         float|None  = None

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(self, error: float, dt: float | None = None) -> float:
        """
        Compute and return the PID correction for *error*.

        error : current error (e.g. offset_x in pixels)
        dt    : elapsed seconds since last call.
                Pass None to measure automatically from the wall clock.
        """
        now = time.monotonic()

        if dt is None:
            dt = (now - self._last_time) if self._last_time is not None else 0.0
        self._last_time = now

        # Deadband — treat tiny errors as zero to prevent jitter
        if abs(error) < self.deadband:
            error = 0.0

        # Proportional
        p_term = self.kp * error

        # Integral with anti-windup clamp
        if dt > 0:
            self._integral += error * dt
            self._integral = max(-self.integral_limit,
                                 min(self.integral_limit, self._integral))
        i_term = self.ki * self._integral

        # Derivative on measurement (avoids kick on setpoint jumps)
        d_term      = 0.0
        measurement = -error  # measurement = centre − moon_position
        if dt > 0 and self._last_measurement is not None:
            d_meas = (measurement - self._last_measurement) / dt
            d_term = -self.kd * d_meas
        self._last_measurement = measurement

        output = p_term + i_term + d_term

        # Clamp output and back-off integral if saturated
        if output > self.max_output:
            output = self.max_output
            if error > 0:
                self._integral -= error * dt
        elif output < -self.max_output:
            output = -self.max_output
            if error < 0:
                self._integral -= error * dt

        return output

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all internal state. Call when detection is lost."""
        self._integral         = 0.0
        self._last_measurement = None
        self._last_time        = None

    @property
    def integral(self) -> float:
        return self._integral

    def __repr__(self) -> str:
        return (f"PID(kp={self.kp}, ki={self.ki}, kd={self.kd}, "
                f"max_output={self.max_output}, deadband={self.deadband})")

    # ------------------------------------------------------------------
    # Auto-tune stub (future — Ziegler-Nichols relay method)
    # ------------------------------------------------------------------

    def auto_tune(self, output_step: float = 50.0):
        """
        TODO: Ziegler-Nichols relay auto-tuning.

        Procedure:
          1. Set ki=0, kd=0.
          2. Apply relay (bang-bang) output ±output_step.
          3. Measure oscillation period Tu and amplitude.
          4. Compute Ku = 4 × output_step / (π × amplitude).
          5. kp = 0.6·Ku,  ki = 2·kp/Tu,  kd = kp·Tu/8.

        Requires a live control loop with real motor feedback.
        """
        raise NotImplementedError("Auto-tune not yet implemented.")
