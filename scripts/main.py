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
      PID corrections are converted to steps and sent to two StepperMotor
      instances (azimuth + elevation).
      A full HUD window is shown — identical to simulate mode — so you
      can watch the PID work in real time while the motors run.

      Camera priority: picamera2 → webcam (index 0) → error.
      This means the script still runs if picamera2 is not available or
      fails to open (e.g. wrong ribbon cable, missing libcamera stack).

Controls (both modes):
  SPACE  — pause / resume
  R      — restart video (simulate only)
  Q/ESC  — quit

Usage:
  python scripts/main.py                              # simulate, default video
  python scripts/main.py --mode simulate --path videos/test.mp4
  python scripts/main.py --mode live                  # Raspberry Pi only
  python scripts/main.py --mode live --camera webcam  # force webcam
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
# Window name — shared by both modes so there is always exactly one window
# ---------------------------------------------------------------------------

WIN = "Telescope — Vision Tracker  (Q to quit)"


# ---------------------------------------------------------------------------
# Camera helper for live mode
# ---------------------------------------------------------------------------

def _open_live_camera(args):
    """
    Try to open the best available camera for live mode.

    Priority (unless --camera is specified):
      1. picamera2  — Raspberry Pi camera module
      2. webcam     — USB webcam via OpenCV (index 0)

    Returns an opened BaseCamera, or None on failure.
    """
    w = args.width  or CFG.camera.width
    h = args.height or CFG.camera.height

    sources = []
    if args.camera == "webcam":
        sources = ["webcam"]
    elif args.camera == "picamera2":
        sources = ["picamera2"]
    else:
        # Auto: try picamera2 first, fall back to webcam
        sources = ["picamera2", "webcam"]

    for source in sources:
        print(f"[camera] Trying {source} …")
        try:
            if source == "picamera2":
                cam = create_camera("picamera2", width=w, height=h)
            else:
                cam = create_camera("webcam", index=args.webcam_index or 0)

            if cam.open():
                print(f"[camera] Opened {source}  ({cam.width}×{cam.height})")
                return cam
            else:
                print(f"[camera] {source} reported open() = False, skipping.")
        except Exception as exc:
            print(f"[camera] {source} failed: {exc}")

    return None


# ---------------------------------------------------------------------------
# Shared HUD drawing
# ---------------------------------------------------------------------------

def _build_hud(frame, result, pid_x, pid_y, correction_x, correction_y,
               dt, frame_count, mode_label, extra_rows=None):
    """
    Draw all HUD elements onto *frame* (in-place) and return it.

    Parameters
    ----------
    extra_rows : list of (label, value) tuples appended to the info panel.
                 Used by live mode to show motor step counts.
    """
    h, w  = frame.shape[:2]
    cx, cy = w // 2, h // 2

    # Target centre — red crosshair
    draw_crosshair(frame, cx, cy, (0, 0, 220), size=18, thickness=2)
    cv2.circle(frame, (cx, cy), 3, (0, 0, 220), -1)

    if result.found:
        # Real moon — green circle + crosshair
        cv2.circle(frame, (result.cx, result.cy), result.radius,
                   (0, 210, 0), 2, cv2.LINE_AA)
        draw_crosshair(frame, result.cx, result.cy, (0, 210, 0))
        cv2.circle(frame, (result.cx, result.cy), 3, (0, 210, 0), -1)

        # PID correction arrow from centre toward correction direction
        arr_x = max(0, min(w - 1, cx + int(correction_x * 0.4)))
        arr_y = max(0, min(h - 1, cy + int(correction_y * 0.4)))
        draw_arrow(frame, cx, cy, arr_x, arr_y, (0, 200, 255), thickness=2)

        nx, ny = result.offset_normalized
        steps_x = int(correction_x * CFG.motor.steps_per_pixel)
        steps_y = int(correction_y * CFG.motor.steps_per_pixel)

        info = [
            ("Mode",         mode_label),
            ("Moon centre",  f"({result.cx}, {result.cy})"),
            ("Error X",      f"{result.offset_x:+d} px"),
            ("Error Y",      f"{result.offset_y:+d} px"),
            ("Error norm X", f"{nx:+.3f}"),
            ("Error norm Y", f"{ny:+.3f}"),
            ("PID out X",    f"{correction_x:+.1f}"),
            ("PID out Y",    f"{correction_y:+.1f}"),
            ("Steps X",      f"{steps_x:+d}"),
            ("Steps Y",      f"{steps_y:+d}"),
            ("Integral X",   f"{pid_x.integral:.2f}"),
            ("Integral Y",   f"{pid_y.integral:.2f}"),
            ("dt",           f"{dt * 1000:.1f} ms"),
            ("Frame",        str(frame_count)),
        ]

        draw_error_bars(frame, result.offset_x, result.offset_y)

    else:
        info = [
            ("Mode",  mode_label),
            ("Moon",  "NOT DETECTED"),
            ("Frame", str(frame_count)),
            ("PID",   "reset"),
        ]

    if extra_rows:
        info.extend(extra_rows)

    draw_panel(frame, info, x=8, y=8, width=310)
    draw_legend(frame)
    return frame


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

        h, w   = frame.shape[:2]
        cx, cy = w // 2, h // 2
        result: DetectionResult = detector.detect(frame)
        out = frame.copy()

        # Compute PID first so we can pass corrections into the HUD builder
        correction_x = correction_y = 0.0
        sim_extra = []

        if result.found:
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

            sim_extra = [
                ("Sim offset X", f"{sim_offset_x:+.1f} px"),
                ("Sim offset Y", f"{sim_offset_y:+.1f} px"),
                ("Ghost pos",    f"({ghost_x}, {ghost_y})"),
            ]
        else:
            pid_x.reset()
            pid_y.reset()
            sim_offset_x *= 0.9
            sim_offset_y *= 0.9

        _build_hud(out, result, pid_x, pid_y,
                   correction_x, correction_y,
                   dt, frame_count,
                   mode_label="SIMULATE",
                   extra_rows=sim_extra)

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
    from src.hardware.motor import StepperMotor

    # --- Camera -----------------------------------------------------------
    cam = _open_live_camera(args)
    if cam is None:
        print(
            "[ERROR] No camera could be opened.\n"
            "  • Check the ribbon cable and run: libcamera-hello --list-cameras\n"
            "  • Or pass --camera webcam to use a USB camera."
        )
        return

    # --- Motors -----------------------------------------------------------
    motor_az = StepperMotor(
        dir_pin       = CFG.motor.az_dir_pin,
        step_pin      = CFG.motor.az_step_pin,
        step_delay    = CFG.motor.step_delay,
        steps_per_rev = CFG.motor.steps_per_rev,
    )
    motor_el = StepperMotor(
        dir_pin       = CFG.motor.el_dir_pin,
        step_pin      = CFG.motor.el_step_pin,
        step_delay    = CFG.motor.step_delay,
        steps_per_rev = CFG.motor.steps_per_rev,
    )

    detector  = MoonDetector()
    pid_x     = PID()
    pid_y     = PID()
    last_time = time.monotonic()
    frame_count = 0

    paused = False
    last_frame = None

    # --- Window -----------------------------------------------------------
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    print("Live mode started.")
    print(f"  AZ motor : DIR=GPIO{CFG.motor.az_dir_pin}  STEP=GPIO{CFG.motor.az_step_pin}")
    print(f"  EL motor : DIR=GPIO{CFG.motor.el_dir_pin}  STEP=GPIO{CFG.motor.el_step_pin}")
    print("  Press Q or ESC in the window to quit, SPACE to pause.\n")

    try:
        while True:
            now = time.monotonic()
            dt  = now - last_time
            last_time = now

            # ---- Frame acquisition ---------------------------------------
            if not paused:
                ok, frame = cam.read()
                if not ok:
                    print("[WARN] Frame read failed — skipping.")
                    # Still show last good frame so the window stays alive
                    if last_frame is not None:
                        cv2.imshow(WIN, last_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord('q'), 27):
                        break
                    continue
                last_frame = frame
                frame_count += 1
            else:
                frame = last_frame
                dt    = 0.0

            # ---- Detection + PID -----------------------------------------
            result = detector.detect(frame)
            out    = frame.copy()

            correction_x = correction_y = 0.0
            steps_x = steps_y = 0
            live_extra = []

            if result.found:
                correction_x = pid_x.update(float(result.offset_x), dt)
                correction_y = pid_y.update(float(result.offset_y), dt)

                steps_x = int(correction_x * CFG.motor.steps_per_pixel)
                steps_y = int(correction_y * CFG.motor.steps_per_pixel)

                # Drive motors only when not paused
                if not paused:
                    if steps_x:
                        motor_az.step(steps_x)
                    if steps_y:
                        motor_el.step(steps_y)

                live_extra = [
                    ("Motor AZ steps", f"{steps_x:+d}"),
                    ("Motor EL steps", f"{steps_y:+d}"),
                ]

                print(
                    f"err=({result.offset_x:+4d},{result.offset_y:+4d})px  "
                    f"pid=({correction_x:+6.1f},{correction_y:+6.1f})  "
                    f"steps=({steps_x:+4d},{steps_y:+4d})"
                )
            else:
                pid_x.reset()
                pid_y.reset()
                print("Moon not detected — PID reset")

            # ---- HUD -----------------------------------------------------
            _build_hud(out, result, pid_x, pid_y,
                       correction_x, correction_y,
                       dt, frame_count,
                       mode_label="LIVE",
                       extra_rows=live_extra)

            if paused:
                h, w = out.shape[:2]
                cv2.putText(out, "PAUSED", (w // 2 - 38, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

            cv2.imshow(WIN, out)

            # ---- Key handling --------------------------------------------
            # waitKey(1) keeps the window responsive without stalling capture
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            elif key == ord(' '):
                paused = not paused
                state = "PAUSED — motors stopped" if paused else "RESUMED"
                print(f"[{state}]")

    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")
    finally:
        motor_az.cleanup()
        motor_el.cleanup()
        cam.close()
        cv2.destroyAllWindows()
        print("Done.")


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
    parser.add_argument(
        "--camera", default="auto", choices=["auto", "picamera2", "webcam"],
        help=(
            "Camera source for live mode (default: auto). "
            "'auto' tries picamera2 first, falls back to webcam."
        ),
    )
    parser.add_argument(
        "--webcam-index", type=int, default=0,
        help="USB webcam device index for --camera webcam (default: 0)",
    )
    parser.add_argument("--width",  type=int, default=None, help="Camera width (live)")
    parser.add_argument("--height", type=int, default=None, help="Camera height (live)")
    args = parser.parse_args()

    if args.mode == "simulate":
        run_simulate(args)
    else:
        run_live(args)