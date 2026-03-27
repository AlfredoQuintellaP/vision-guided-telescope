"""
main.py — Telescope main loop + PID simulation mode

Two modes selectable via --mode flag:

  simulate  (default)
      Runs on a video file. Does NOT move any motor.
      Shows what the PID *would* command, and draws a ghost crosshair
      showing where the moon would be if the motor were following the
      PID corrections. Useful for tuning gains before touching hardware.

  live
      Runs with the real camera + real motors (Raspberry Pi only).
      The PID corrections are converted to stepper steps and sent to
      the two StepperMotor instances.

Controls (both modes):
  SPACE  — pause / resume
  R      — restart video (simulate mode only)
  Q/ESC  — quit

Usage:
  python src/main.py                        # simulate with test.mp4
  python src/main.py --mode simulate --path videos/test.mp4
  python src/main.py --mode live            # Raspberry only
"""

import argparse
import time
import cv2
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from camera import create_camera
from moon_detector import DetectorConfig, MoonDetector, DetectionResult
from pid import PID


# ---------------------------------------------------------------------------
# Config — tweak these before going live
# ---------------------------------------------------------------------------

DETECTOR_CFG = DetectorConfig(
    blur_kernel=5,
    param1=60,
    param2=35,
    min_radius=30,
    max_radius=200,
)

PID_CFG = dict(
    kp=0.6,
    ki=0.02,
    kd=0.15,
    max_output=100.0,
    integral_limit=60.0,
    deadband=3.0,       # pixels — ignore tiny errors to avoid jitter
)

# How many stepper steps per pixel of correction (tune after calibration)
STEPS_PER_PIXEL = 0.5

# Simulated motor lag: fraction of correction applied per frame (0–1)
# 1.0 = instant (ideal), 0.3 = sluggish motor response
SIM_MOTOR_RESPONSE = 0.4


# ---------------------------------------------------------------------------
# Overlay helpers
# ---------------------------------------------------------------------------

def draw_crosshair(img, x, y, color, size=14, thickness=1):
    cv2.line(img, (x - size, y), (x + size, y), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x, y - size), (x, y + size), color, thickness, cv2.LINE_AA)


def draw_arrow(img, x0, y0, x1, y1, color, thickness=1):
    cv2.arrowedLine(img, (x0, y0), (x1, y1), color, thickness,
                    cv2.LINE_AA, tipLength=0.2)


def draw_panel(img, lines: list[tuple[str, str]], x, y, width=310):
    """Semi-transparent info panel. lines = [(label, value), ...]"""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thick = 0.45, 1
    lh = 19
    pad = 8
    h = len(lines) * lh + 2 * pad

    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + width, y + h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

    for i, (label, value) in enumerate(lines):
        yy = y + pad + (i + 1) * lh - 4
        cv2.putText(img, label, (x + pad, yy),
                    font, scale, (160, 160, 160), thick, cv2.LINE_AA)
        cv2.putText(img, value, (x + pad + 160, yy),
                    font, scale, (230, 230, 230), thick, cv2.LINE_AA)


def bar(value, max_val, width=80) -> str:
    """ASCII progress bar for the panel."""
    filled = int(abs(value) / max_val * width)
    filled = min(filled, width)
    sign = "+" if value >= 0 else "-"
    return sign + "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Simulate mode
# ---------------------------------------------------------------------------

def run_simulate(args):
    cam = create_camera(source="video", path=args.path, loop=True)
    if not cam.open():
        print("[ERROR] Could not open video:", args.path)
        return

    detector = MoonDetector(DETECTOR_CFG)
    pid_x = PID(**PID_CFG)
    pid_y = PID(**PID_CFG)

    # Simulated motor position offset (pixels) — starts at 0 (centered)
    sim_offset_x = 0.0
    sim_offset_y = 0.0

    paused = False
    frame_count = 0
    last_time = time.monotonic()
    last_frame = None

    WIN = "Telescope — PID Simulation (Q to quit)"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    print("PID simulation started.")
    print("  Green crosshair  = moon actual position")
    print("  Blue crosshair   = where moon WOULD be if motor followed PID")
    print("  Red crosshair    = image center (target)")
    print("  Arrow            = PID correction direction\n")

    while True:
        now = time.monotonic()
        dt = now - last_time
        last_time = now

        if not paused:
            ok, frame = cam.read()
            if not ok:
                break
            last_frame = frame
            frame_count += 1
        else:
            frame = last_frame
            dt = 0.0

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        result: DetectionResult = detector.detect(frame)
        out = frame.copy()

        # Image center (target) — red crosshair
        draw_crosshair(out, cx, cy, (0, 0, 220), size=18, thickness=2)
        cv2.circle(out, (cx, cy), 3, (0, 0, 220), -1)

        if result.found:
            # Real moon position — green circle + crosshair
            cv2.circle(out, (result.cx, result.cy), result.radius,
                       (0, 210, 0), 2, cv2.LINE_AA)
            draw_crosshair(out, result.cx, result.cy, (0, 210, 0))
            cv2.circle(out, (result.cx, result.cy), 3, (0, 210, 0), -1)

            # PID update
            correction_x = pid_x.update(float(result.offset_x), dt)
            correction_y = pid_y.update(float(result.offset_y), dt)

            # Simulate motor moving (gradual approach)
            sim_offset_x += (correction_x - sim_offset_x) * SIM_MOTOR_RESPONSE
            sim_offset_y += (correction_y - sim_offset_y) * SIM_MOTOR_RESPONSE

            # Ghost moon position if motor were correcting
            ghost_x = int(result.cx - sim_offset_x)
            ghost_y = int(result.cy - sim_offset_y)
            ghost_x = max(0, min(w - 1, ghost_x))
            ghost_y = max(0, min(h - 1, ghost_y))

            # Ghost — blue crosshair
            draw_crosshair(out, ghost_x, ghost_y, (220, 100, 0), size=14)
            cv2.circle(out, (ghost_x, ghost_y), 3, (220, 100, 0), -1)

            # Arrow from center → correction direction
            arr_x = cx + int(correction_x * 0.4)
            arr_y = cy + int(correction_y * 0.4)
            arr_x = max(0, min(w - 1, arr_x))
            arr_y = max(0, min(h - 1, arr_y))
            draw_arrow(out, cx, cy, arr_x, arr_y, (0, 200, 255), thickness=2)

            # Stepper steps that would be sent
            steps_x = int(correction_x * STEPS_PER_PIXEL)
            steps_y = int(correction_y * STEPS_PER_PIXEL)

            nx, ny = result.offset_normalized
            info = [
                ("Moon center",    f"({result.cx}, {result.cy})"),
                ("Error X",        f"{result.offset_x:+d} px"),
                ("Error Y",        f"{result.offset_y:+d} px"),
                ("Error norm X",   f"{nx:+.3f}"),
                ("Error norm Y",   f"{ny:+.3f}"),
                ("PID out X",      f"{correction_x:+.1f}"),
                ("PID out Y",      f"{correction_y:+.1f}"),
                ("Steps X",        f"{steps_x:+d}"),
                ("Steps Y",        f"{steps_y:+d}"),
                ("Sim offset X",   f"{sim_offset_x:+.1f} px"),
                ("Sim offset Y",   f"{sim_offset_y:+.1f} px"),
                ("Ghost pos",      f"({ghost_x}, {ghost_y})"),
                ("Integral X",     f"{pid_x.terms['integral']:.2f}"),
                ("Integral Y",     f"{pid_y.terms['integral']:.2f}"),
                ("dt",             f"{dt*1000:.1f} ms"),
                ("Frame",          f"{frame_count}"),
            ]
        else:
            # Detection lost — reset PIDs to avoid stale integral
            pid_x.reset()
            pid_y.reset()
            sim_offset_x *= 0.9   # decay simulation slowly
            sim_offset_y *= 0.9

            info = [
                ("Moon",    "NOT DETECTED"),
                ("Frame",   str(frame_count)),
                ("PID",     "reset"),
            ]

        draw_panel(out, info, x=8, y=8, width=310)

        # Error bar overlay (bottom of frame)
        if result.found:
            bar_h = 18
            bar_y = h - bar_h - 6
            # X error bar
            half = w // 2
            ex_len = int(result.offset_x * 0.3)
            cv2.rectangle(out, (half, bar_y), (half + ex_len, bar_y + bar_h // 2 - 1),
                          (0, 180, 255), -1)
            # Y error bar (vertical, right side)
            ey_len = int(result.offset_y * 0.3)
            bx = w - 18
            cv2.rectangle(out, (bx, h // 2), (bx + bar_h // 2 - 1, h // 2 + ey_len),
                          (0, 255, 180), -1)

        if paused:
            cv2.putText(out, "PAUSED", (w // 2 - 38, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        # Legend (bottom left)
        legend = [
            ("Green",  "real moon"),
            ("Blue",   "ghost (PID corrected)"),
            ("Red",    "target center"),
            ("Cyan",   "PID correction arrow"),
        ]
        colors = [(0,210,0), (220,100,0), (0,0,220), (0,200,255)]
        for i, ((lbl, txt), col) in enumerate(zip(legend, colors)):
            lx, ly = 8, h - 90 + i * 18
            cv2.rectangle(out, (lx, ly), (lx + 12, ly + 10), col, -1)
            cv2.putText(out, f"{lbl}: {txt}", (lx + 18, ly + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)

        cv2.imshow(WIN, out)

        key = cv2.waitKey(25) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('r'):
            cam.close()
            cam.open()
            pid_x.reset()
            pid_y.reset()
            sim_offset_x = sim_offset_y = 0.0
            frame_count = 0
            print("Restarted.")

    cam.close()
    cv2.destroyAllWindows()
    print("Done.")


# ---------------------------------------------------------------------------
# Live mode (Raspberry Pi)
# ---------------------------------------------------------------------------

def run_live(args):
    try:
        from motor import StepperMotor
    except ImportError:
        print("[ERROR] motor.py not found in src/")
        return

    cam = create_camera(source="picamera2",
                        width=args.width, height=args.height)
    if not cam.open():
        print("[ERROR] Could not open Pi Camera.")
        return

    detector = MoonDetector(DETECTOR_CFG)
    pid_x = PID(**PID_CFG)
    pid_y = PID(**PID_CFG)

    motor_x = StepperMotor()   # azimuth
    motor_y = StepperMotor(    # elevation — swap pins if needed
        pin_in1=2, pin_in2=3, pin_in3=14, pin_in4=22
    )

    last_time = time.monotonic()
    print("Live mode started. Ctrl+C to stop.")

    try:
        while True:
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            ok, frame = cam.read()
            if not ok:
                continue

            result = detector.detect(frame)

            if result.found:
                correction_x = pid_x.update(float(result.offset_x), dt)
                correction_y = pid_y.update(float(result.offset_y), dt)

                steps_x = int(correction_x * STEPS_PER_PIXEL)
                steps_y = int(correction_y * STEPS_PER_PIXEL)

                if steps_x != 0:
                    motor_x.step(steps_x)
                if steps_y != 0:
                    motor_y.step(steps_y)

                motor_x.release()
                motor_y.release()

                print(f"err=({result.offset_x:+4d},{result.offset_y:+4d})px  "
                      f"pid=({correction_x:+6.1f},{correction_y:+6.1f})  "
                      f"steps=({steps_x:+4d},{steps_y:+4d})")
            else:
                pid_x.reset()
                pid_y.reset()
                print("Moon not detected — PID reset")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        motor_x.cleanup()
        motor_y.cleanup()
        cam.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telescope main loop")
    parser.add_argument("--mode", default="simulate",
                        choices=["simulate", "live"],
                        help="'simulate' = video + PID overlay  |  'live' = Pi camera + motors")
    parser.add_argument("--path", default="videos/test.mp4",
                        help="Video path (simulate mode)")
    parser.add_argument("--width",  type=int, default=1280,
                        help="Camera width (live mode)")
    parser.add_argument("--height", type=int, default=720,
                        help="Camera height (live mode)")
    args = parser.parse_args()

    if args.mode == "simulate":
        run_simulate(args)
    else:
        run_live(args)
