"""
settings.py — Central configuration for the telescope system.

All tunable parameters live here. Import this in any module instead of
scattering magic numbers across the codebase.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Moon detection
# ---------------------------------------------------------------------------

@dataclass
class DetectorSettings:
    """
    Parameters for HoughCircles-based moon detection.

    Key parameters to tune:
      param2      — accumulator threshold; HIGHER = fewer detections, fewer false positives.
                    Old value (35) produced 10–35 false circles per frame.
                    New value (40) yields a single clean detection or none.
      param1      — upper Canny threshold; too low lets noise edges through.
      blur_kernel — must be odd; larger smooths more noise at cost of edge sharpness.
      min_radius  — set just below the smallest expected moon radius in pixels.
      max_radius  — set just above the largest expected moon radius in pixels.

    The detector also scores candidates by interior brightness and returns only
    the brightest circle, which eliminates residual false positives even when
    multiple circles pass the Hough filter.
    """

    # Pre-processing
    blur_kernel: int   = 7      # GaussianBlur kernel size (must be odd). Was 5.
    blur_sigma: float  = 2.0    # GaussianBlur sigma. Was 0 (auto). Explicit helps.

    # HoughCircles
    dp: float          = 1.2    # Accumulator resolution ratio (1 = image resolution).
    min_dist: int      = 80     # Minimum distance between circle centres (px). Was 50.
    param1: int        = 100    # Upper Canny threshold. Was 60 — too permissive.
    param2: int        = 40     # Accumulator votes threshold. Was 35 — far too low.
    min_radius: int    = 40     # Minimum radius (px). Was 30.
    max_radius: int    = 280    # Maximum radius (px). Was 200 — raised for large moons.

    # Candidate selection
    # When multiple circles pass HoughCircles, pick the one with the highest
    # mean brightness inside its area (the moon is always the brightest object).
    use_brightness_selection: bool = True


# ---------------------------------------------------------------------------
# PID controller
# ---------------------------------------------------------------------------

@dataclass
class PIDSettings:
    """
    PID gains and limits for a single axis (X or Y).
    Both axes use the same defaults; override per-axis if needed.
    """
    kp: float             = 0.6
    ki: float             = 0.02
    kd: float             = 0.15
    max_output: float     = 100.0
    integral_limit: float = 60.0
    deadband: float       = 3.0   # pixels — ignore errors smaller than this


# ---------------------------------------------------------------------------
# Motor / simulation
# ---------------------------------------------------------------------------

@dataclass
class MotorSettings:
    """
    Stepper motor parameters for STEP/DIR driver boards (A4988 / DRV8825).

    Each axis uses two GPIO pins:
      dir_pin  — sets rotation direction (HIGH = CW, LOW = CCW)
      step_pin — one rising edge = one step

    Steps per revolution depends on your motor + microstepping config:
      Full step  : 200  (1.8° motor)
      Half step  : 400
      1/16 step  : 3200  (typical for smooth tracking)
    """

    # Azimuth motor GPIO pins (BCM numbering)
    az_dir_pin:  int = 26
    az_step_pin: int = 19

    # Elevation motor GPIO pins
    el_dir_pin:  int = 21
    el_step_pin: int = 20

    # Step timing
    step_delay: float = 0.0005   # seconds between steps (~2000 steps/s max)

    # Motor resolution — change if you use microstepping
    steps_per_rev: int = 200     # 200 = 1.8° motor, full step

    # How many stepper steps per pixel of PID correction
    steps_per_pixel: float = 0.5


@dataclass
class SimSettings:
    """Parameters for the PID simulation / video replay mode."""

    # Fraction of PID correction applied per frame (0 = frozen, 1 = instant).
    # Models motor inertia / lag.
    motor_response: float = 0.4

    video_path: str = "videos/test.mp4"
    loop_video: bool = True


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@dataclass
class CameraSettings:
    """Live camera settings (Raspberry Pi only)."""
    width: int  = 1280
    height: int = 720


# ---------------------------------------------------------------------------
# Top-level bundle — import this one object everywhere
# ---------------------------------------------------------------------------

@dataclass
class Config:
    detector: DetectorSettings = field(default_factory=DetectorSettings)
    pid:      PIDSettings      = field(default_factory=PIDSettings)
    motor:    MotorSettings    = field(default_factory=MotorSettings)
    sim:      SimSettings      = field(default_factory=SimSettings)
    camera:   CameraSettings   = field(default_factory=CameraSettings)


# Singleton — modules do `from config import CFG`
CFG = Config()
