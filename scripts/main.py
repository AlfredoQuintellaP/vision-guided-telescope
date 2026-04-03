"""
scripts/main.py — Telescope main loop.

Two modes (--mode flag):

  simulate  (default)
      Runs on a video file. No motors are moved.
      Shows what the PID *would* command and draws a ghost crosshair
      showing where the moon would be if the motor followed the PID.
      Use this to tune gains and detector parameters before any hardware.

  live
      Runs with the real Pi Camera + stepper motors (Raspberry Pi only).
      PID corrections are converted to half-steps and sent to two
      StepperMotor instances (azimuth + elevation).

Controls (both modes):
  SPACE  — pause / resume
  R      — restart video (simulate only)
  Q/ESC  — quit

Usage:
  python scripts/main.py                              # simulate, default video
  python scripts/main.py --mode simulate --path videos/test.mp4
  python scripts/main.py --mode live                  # Raspberry Pi only
"""

import argparse
import time
import sys
import os

import cv2
import numpy as np

# Make project root importable regardless of working directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import CFG
from src.detection  import MoonDetector, DetectionResult
from src.control    import PID
from src.hardware   import create_camera
from src.utils      import (draw_crosshair, draw_arrow,
                             draw_panel, draw_error_bars, draw_legend)


# ---------------------------------------------------------------------------
# Simulate mode
# ---------------------------------------------------------------------------

def run_simulate(args) -> None:
    path = args.path or CFG.sim.video_path
    cam  = create_camera("video", path=path, loop=CFG.sim.loop_video)

    if not cam.open():
        print(f"[ERROR] Could not open video: {path}")
        return

    detector = MoonDetector()
    pid_x    = PID()
    pid_y    = PID()

    sim_offset_x = 0.0
    sim_offset_y = 0.0

    paused      = False
    frame_count = 0
    last_time   = time.monotonic()
    last_frame  = None

    WIN = "Telescope — PID Simulation  (Q to quit)"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    print("PID simulation started.")
    print("  Green  crosshair = moon actual position")
    print("  Blue   crosshair = where moon WOULD be if motor followed PID")
    print("  Red    crosshair = image centre (target)")
    print("  Cyan   arrow     = PID correction direction\n")

    while True:
        now = time.monotonic()
        dt  = now - last_time
        last_time = now

        if not paused:
            ok, frame = cam.read()
            if not ok:
                break
            last_frame  = frame
            frame_count += 1
        else:
            frame = last_frame
            dt    = 0.0

        h, w  = frame.shape[:2]
        cx, cy = w // 2, h // 2
        result: DetectionResult = detector.detect(frame)
        out = frame.copy()

        # Target centre — red crosshair
        draw_crosshair(out, cx, cy, (0, 0, 220), size=18, thickness=2)
        cv2.circle(out, (cx, cy), 3, (0, 0, 220), -1)

        if result.found:
            # Real moon — green circle + crosshair
            cv2.circle(out, (result.cx, result.cy), result.radius,
                       (0, 210, 0), 2, cv2.LINE_AA)
            draw_crosshair(out, result.cx, result.cy, (0, 210, 0))
            cv2.circle(out, (result.cx, result.cy), 3, (0, 210, 0), -1)

            correction_x = pid_x.update(float(result.offset_x), dt)
            correction_y = pid_y.update(float(result.offset_y), dt)

            # Simulated motor response (gradual approach)
            r = CFG.sim.motor_response
            sim_offset_x += (correction_x - sim_offset_x) * r
            sim_offset_y += (correction_y - sim_offset_y) * r

            # Ghost position (where moon would be after motor correction)
            ghost_x = max(0, min(w - 1, int(result.cx - sim_offset_x)))
            ghost_y = max(0, min(h - 1, int(result.cy - sim_offset_y)))

            # Ghost — blue crosshair
            draw_crosshair(out, ghost_x, ghost_y, (220, 100, 0), size=14)
            cv2.circle(out, (ghost_x, ghost_y), 3, (220, 100, 0), -1)

            # PID correction arrow
            arr_x = max(0, min(w - 1, cx + int(correction_x * 0.4)))
            arr_y = max(0, min(h - 1, cy + int(correction_y * 0.4)))
            draw_arrow(out, cx, cy, arr_x, arr_y, (0, 200, 255), thickness=2)

            steps_x = int(correction_x * CFG.motor.steps_per_pixel)
            steps_y = int(correction_y * CFG.motor.steps_per_pixel)
            nx, ny  = result.offset_normalized

            info = [
                ("Moon centre",   f"({result.cx}, {result.cy})"),
                ("Error X",       f"{result.offset_x:+d} px"),
                ("Error Y",       f"{result.offset_y:+d} px"),
                ("Error norm X",  f"{nx:+.3f}"),
                ("Error norm Y",  f"{ny:+.3f}"),
                ("PID out X",     f"{correction_x:+.1f}"),
                ("PID out Y",     f"{correction_y:+.1f}"),
                ("Steps X",       f"{steps_x:+d}"),
                ("Steps Y",       f"{steps_y:+d}"),
                ("Sim offset X",  f"{sim_offset_x:+.1f} px"),
                ("Sim offset Y",  f"{sim_offset_y:+.1f} px"),
                ("Ghost pos",     f"({ghost_x}, {ghost_y})"),
                ("Integral X",    f"{pid_x.integral:.2f}"),
                ("Integral Y",    f"{pid_y.integral:.2f}"),
                ("dt",            f"{dt * 1000:.1f} ms"),
                ("Frame",         str(frame_count)),
            ]

            draw_error_bars(out, result.offset_x, result.offset_y)

        else:
            pid_x.reset()
            pid_y.reset()
            sim_offset_x *= 0.9
            sim_offset_y *= 0.9

            info = [
                ("Moon",  "NOT DETECTED"),
                ("Frame", str(frame_count)),
                ("PID",   "reset"),
            ]

        draw_panel(out, info, x=8, y=8, width=310)
        draw_legend(out)

        if paused:
            cv2.putText(out, "PAUSED", (w // 2 - 38, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        cv2.imshow(WIN, out)
        key = cv2.waitKey(25) & 0xFF

        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('r'):
            cam.close(); cam.open()
            pid_x.reset(); pid_y.reset()
            sim_offset_x = sim_offset_y = 0.0
            frame_count  = 0
            print("Restarted.")

    cam.close()
    cv2.destroyAllWindows()
    print("Done.")


# ---------------------------------------------------------------------------
# Live mode (Raspberry Pi only)
# ---------------------------------------------------------------------------

def run_live(args) -> None:
    from src.hardware import StepperMotor

    cam = create_camera(
        "picamera2",
        width  = args.width  or CFG.camera.width,
        height = args.height or CFG.camera.height,
    )
    if not cam.open():
        print("[ERROR] Could not open Pi Camera.")
        return

    detector = MoonDetector()
    pid_x    = PID()
    pid_y    = PID()

    # Azimuth motor uses default pins; elevation uses config override
    motor_x = StepperMotor(
        pin_in1=CFG.motor.az_pin_in1, pin_in2=CFG.motor.az_pin_in2,
        pin_in3=CFG.motor.az_pin_in3, pin_in4=CFG.motor.az_pin_in4,
        step_delay=CFG.motor.step_delay,
    )
    motor_y = StepperMotor(
        pin_in1=CFG.motor.el_pin_in1, pin_in2=CFG.motor.el_pin_in2,
        pin_in3=CFG.motor.el_pin_in3, pin_in4=CFG.motor.el_pin_in4,
        step_delay=CFG.motor.step_delay,
    )

    last_time = time.monotonic()
    print("Live mode started.  Ctrl+C to stop.")

    try:
        while True:
            now = time.monotonic()
            dt  = now - last_time
            last_time = now

            ok, frame = cam.read()
            if not ok:
                continue

            result = detector.detect(frame)

            if result.found:
                correction_x = pid_x.update(float(result.offset_x), dt)
                correction_y = pid_y.update(float(result.offset_y), dt)

                steps_x = int(correction_x * CFG.motor.steps_per_pixel)
                steps_y = int(correction_y * CFG.motor.steps_per_pixel)

                if steps_x:
                    motor_x.step(steps_x)
                if steps_y:
                    motor_y.step(steps_y)

                motor_x.release()
                motor_y.release()

                print(
                    f"err=({result.offset_x:+4d},{result.offset_y:+4d})px  "
                    f"pid=({correction_x:+6.1f},{correction_y:+6.1f})  "
                    f"steps=({steps_x:+4d},{steps_y:+4d})"
                )
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
    parser.add_argument(
        "--mode", default="simulate", choices=["simulate", "live"],
        help="'simulate' = video + PID overlay  |  'live' = Pi camera + motors",
    )
    parser.add_argument(
        "--path", default=None,
        help="Video path for simulate mode (default: videos/test.mp4)",
    )
    parser.add_argument("--width",  type=int, default=None, help="Camera width (live)")
    parser.add_argument("--height", type=int, default=None, help="Camera height (live)")
    args = parser.parse_args()

    if args.mode == "simulate":
        run_simulate(args)
    else:
        run_live(args)
