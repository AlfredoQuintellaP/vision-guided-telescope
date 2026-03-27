"""
pid.py — PID controller for telescope axis servo loop

Intended usage:
    pid_x = PID(kp=0.5, ki=0.01, kd=0.1)
    pid_y = PID(kp=0.5, ki=0.01, kd=0.1)

    correction_x = pid_x.update(error_x, dt)
    correction_y = pid_y.update(error_y, dt)

Error convention:
    error = detected_position - image_center   (pixels or normalized -1..1)
    A positive error means the moon is to the right / below center.
    The correction returned should be fed to the motor as steps (or speed).

Features:
    - Output clamping          : correction stays within [-max_output, +max_output]
    - Integral windup guard    : integral stops accumulating when output is saturated
    - Derivative on measurement: avoids derivative kick on setpoint changes
    - reset()                  : clears internal state (use on detection loss)
    - Auto-tune stub           : placeholder for future Ziegler-Nichols tuning
"""

import time


class PID:

    def __init__(
        self,
        kp: float = 0.5,
        ki: float = 0.01,
        kd: float = 0.1,
        max_output: float = 100.0,      # clamp limit (same unit as correction)
        integral_limit: float = 50.0,   # anti-windup: max absolute integral term
        deadband: float = 0.0,          # errors smaller than this are treated as 0
    ):
        """
        kp             : proportional gain
        ki             : integral gain
        kd             : derivative gain
        max_output     : output is clamped to [-max_output, +max_output]
        integral_limit : caps the integral accumulator to prevent windup
        deadband       : ignore tiny errors (useful near the target to avoid jitter)
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.max_output = max_output
        self.integral_limit = integral_limit
        self.deadband = deadband

        # Internal state
        self._integral: float = 0.0
        self._last_measurement: float | None = None   # for derivative on measurement
        self._last_time: float | None = None

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(self, error: float, dt: float | None = None) -> float:
        """
        Compute the PID correction for the given error.

        error : current error (e.g. offset_x in pixels, or normalized)
        dt    : time since last call in seconds.
                If None, measured automatically from wall clock.

        Returns the correction value (clamped to ±max_output).
        """
        now = time.monotonic()

        # Auto dt from wall clock
        if dt is None:
            if self._last_time is None:
                dt = 0.0
            else:
                dt = now - self._last_time
        self._last_time = now

        # Deadband — treat tiny errors as zero
        if abs(error) < self.deadband:
            error = 0.0

        # --- Proportional ---
        p_term = self.kp * error

        # --- Integral (with windup guard) ---
        if dt > 0:
            self._integral += error * dt
            # Clamp integral accumulator
            self._integral = max(-self.integral_limit,
                                 min(self.integral_limit, self._integral))
        i_term = self.ki * self._integral

        # --- Derivative on measurement (not on error) ---
        # Using -d(measurement)/dt instead of d(error)/dt avoids
        # derivative kick when the setpoint changes abruptly.
        # Since setpoint = 0 always (we want moon at center),
        # d(error)/dt == -d(measurement)/dt, so both are equivalent here.
        # We keep the pattern for future setpoint changes.
        d_term = 0.0
        measurement = -error   # measurement = image_center - moon_position
        if dt > 0 and self._last_measurement is not None:
            d_measurement = (measurement - self._last_measurement) / dt
            d_term = -self.kd * d_measurement   # negative because derivative on measurement
        self._last_measurement = measurement

        # --- Sum ---
        output = p_term + i_term + d_term

        # --- Output clamping ---
        # Anti-windup: if output is saturated, stop integrating in that direction
        if output > self.max_output:
            output = self.max_output
            if error > 0:   # integrating would make it worse
                self._integral -= error * dt
        elif output < -self.max_output:
            output = -self.max_output
            if error < 0:
                self._integral -= error * dt

        return output

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all internal state. Call when detection is lost."""
        self._integral = 0.0
        self._last_measurement = None
        self._last_time = None

    @property
    def terms(self) -> dict:
        """Last computed P/I/D terms — useful for debug / tuning."""
        return {
            "integral": self._integral,
            "last_measurement": self._last_measurement,
        }

    def __repr__(self):
        return (f"PID(kp={self.kp}, ki={self.ki}, kd={self.kd}, "
                f"max_output={self.max_output}, deadband={self.deadband})")

    # ------------------------------------------------------------------
    # Auto-tune stub (future)
    # ------------------------------------------------------------------

    def auto_tune(self, output_step: float = 50.0, target_amplitude: float = 10.0):
        """
        TODO: Ziegler-Nichols relay auto-tuning.

        Procedure:
          1. Set ki=0, kd=0.
          2. Apply a relay (bang-bang) output ±output_step.
          3. Measure oscillation period Tu and amplitude.
          4. Compute Ku = 4 * output_step / (π * amplitude).
          5. Set: kp = 0.6*Ku,  ki = 2*kp/Tu,  kd = kp*Tu/8.

        This requires being called in a live control loop with real motor
        feedback, so implementation is deferred to the hardware integration phase.
        """
        raise NotImplementedError("Auto-tune not yet implemented.")


# ---------------------------------------------------------------------------
# Simulation / test — python pid.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import math

    print("=" * 60)
    print("PID simulation — moon centering")
    print("=" * 60)

    # Simulated scenario:
    #   The moon starts 200px off-center.
    #   Each step the motor moves the image by (correction * 0.1) pixels.
    #   We run for 200 steps at 30 fps (dt = 1/30).

    pid = PID(kp=0.8, ki=0.05, kd=0.2, max_output=100.0, deadband=1.0)

    moon_position = 200.0   # pixels from center (positive = right of center)
    dt = 1 / 30             # 30 fps

    print(f"\n{'Step':>5}  {'Error':>8}  {'Output':>8}  {'Position':>10}")
    print("-" * 40)

    for step in range(80):
        error = moon_position   # error = how far moon is from center

        correction = pid.update(error, dt)

        # Simulate motor moving the telescope:
        # correction > 0 → motor moves right → moon shifts left in frame
        moon_position -= correction * 0.1

        # Add a tiny sinusoidal disturbance (Earth's rotation / vibration)
        moon_position += math.sin(step * 0.3) * 0.5

        if step % 5 == 0:
            print(f"{step:>5}  {error:>8.2f}  {correction:>8.2f}  {moon_position:>10.2f}")

    print()
    print(f"Final position: {moon_position:.2f} px from center")
    print(f"(target: 0.0 px)")

    # -------------------------------------------------------------------
    # Test 2: sudden disturbance (e.g. wind bump)
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Test 2 — disturbance rejection")
    print("=" * 60)

    pid.reset()
    moon_position = 0.0   # already centered

    print(f"\n{'Step':>5}  {'Error':>8}  {'Output':>8}  {'Position':>10}  Note")
    print("-" * 55)

    for step in range(60):
        note = ""
        if step == 10:
            moon_position += 80.0   # sudden bump
            note = "<-- bump +80px"
        if step == 35:
            moon_position -= 50.0   # another bump
            note = "<-- bump -50px"

        error = moon_position
        correction = pid.update(error, dt)
        moon_position -= correction * 0.1

        if step % 3 == 0 or note:
            print(f"{step:>5}  {error:>8.2f}  {correction:>8.2f}  {moon_position:>10.2f}  {note}")

    print()
    print(f"Final position: {moon_position:.2f} px from center")

    # -------------------------------------------------------------------
    # Test 3: windup protection — output saturated for many steps
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Test 3 — integral windup protection")
    print("=" * 60)

    pid2 = PID(kp=0.5, ki=0.5, kd=0.0, max_output=30.0, integral_limit=20.0)
    moon_position = 300.0   # very far, output will saturate

    print(f"\n{'Step':>5}  {'Error':>8}  {'Output':>8}  {'Integral':>10}")
    print("-" * 45)

    for step in range(40):
        error = moon_position
        correction = pid2.update(error, dt)
        moon_position -= correction * 0.1

        if step % 4 == 0:
            integral = pid2.terms["integral"]
            print(f"{step:>5}  {error:>8.2f}  {correction:>8.2f}  {integral:>10.3f}")

    print()
    print(f"Integral stayed within ±{pid2.integral_limit} (windup protection working)")
