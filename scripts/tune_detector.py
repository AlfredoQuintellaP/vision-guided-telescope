"""
scripts/tune_detector.py — Interactive detector tuning tool.

Opens an OpenCV window with the detection overlay and a separate
controls window with sliders for every HoughCircles parameter.
Adjust sliders in real time to find the best settings for your video,
then copy the final values into config/settings.py.

Controls:
  SPACE  — pause / resume
  R      — restart video from the beginning
  S      — save current debug frame to debug_frame_NNNN.png
  Q/ESC  — quit

Usage:
  python scripts/tune_detector.py
  python scripts/tune_detector.py --source video --path videos/test.mp4
  python scripts/tune_detector.py --source webcam
"""

import argparse
import cv2
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import DetectorSettings
from src.detection import MoonDetector
from src.hardware  import create_camera


# ---------------------------------------------------------------------------
# Slider definitions: name → (min, max, default)
# Defaults mirror config/settings.py — the tuned values.
# ---------------------------------------------------------------------------

SLIDERS: dict[str, tuple[int, int, int]] = {
    "blur_kernel": (1,   21,  7),
    "param1":      (10, 300, 100),
    "param2":      (5,  100,  40),
    "min_radius":  (5,  300,  40),
    "max_radius":  (10, 600, 280),
    "min_dist":    (5,  300,  80),
}

WIN_VIDEO   = "Telescope — Detector Tuner  (Q to quit)"
WIN_SLIDERS = "Parameters"


def _noop(_): pass


def _build_windows() -> None:
    cv2.namedWindow(WIN_VIDEO,   cv2.WINDOW_NORMAL)
    cv2.namedWindow(WIN_SLIDERS, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_SLIDERS, 500, 240)

    for name, (lo, hi, default) in SLIDERS.items():
        cv2.createTrackbar(name, WIN_SLIDERS, default, hi, _noop)
        cv2.setTrackbarMin(name, WIN_SLIDERS, lo)


def _read_settings() -> DetectorSettings:
    """Build a DetectorSettings from current slider positions."""
    s = DetectorSettings()
    for name in SLIDERS:
        setattr(s, name, cv2.getTrackbarPos(name, WIN_SLIDERS))
    s.blur_kernel = max(1, s.blur_kernel | 1)   # must be odd
    return s


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args) -> None:
    cam = create_camera(
        source=args.source,
        path=getattr(args, "path", "videos/test.mp4"),
        index=getattr(args, "index", 0),
    )
    if not cam.open():
        print("[ERROR] Could not open camera source.")
        return

    _build_windows()

    detector    = MoonDetector()
    paused      = False
    frame_count = 0
    last_frame  = None

    print("Tuner started — adjust sliders in the 'Parameters' window.")
    print("Shortcuts:  SPACE=pause  R=restart  S=save frame  Q/ESC=quit\n")

    while True:
        if not paused:
            ok, frame = cam.read()
            if not ok:
                print("End of video.")
                break
            last_frame  = frame
            frame_count += 1
        else:
            frame = last_frame

        # Re-read settings every frame so sliders take effect immediately
        detector.settings = _read_settings()

        result = detector.detect(frame)
        debug  = detector.draw_debug(frame, result)

        # Frame counter overlay
        cv2.putText(debug, f"frame {frame_count}",
                    (debug.shape[1] - 130, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)

        if paused:
            cv2.putText(debug, "PAUSED", (debug.shape[1] // 2 - 40, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        cv2.imshow(WIN_VIDEO, debug)

        if frame_count % 30 == 0:
            print(f"[f{frame_count:04d}] {result}")

        key = cv2.waitKey(25) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('r'):
            cam.close(); cam.open()
            frame_count = 0
            print("Restarted.")
        elif key == ord('s') and last_frame is not None:
            fname = f"debug_frame_{frame_count:04d}.png"
            cv2.imwrite(fname, debug)
            print(f"Saved: {fname}")

    cam.close()
    cv2.destroyAllWindows()

    # Print the final slider values as ready-to-paste Python
    s = _read_settings()
    print("\n── Final parameters (copy into config/settings.py) ──")
    print(f"  blur_kernel = {s.blur_kernel}")
    print(f"  param1      = {s.param1}")
    print(f"  param2      = {s.param2}")
    print(f"  min_radius  = {s.min_radius}")
    print(f"  max_radius  = {s.max_radius}")
    print(f"  min_dist    = {s.min_dist}")
    print("─────────────────────────────────────────────────────")

    print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interactive moon detector tuner")
    parser.add_argument("--source", default="video",
                        choices=["video", "webcam", "picamera2"])
    parser.add_argument("--path",  default=os.path.join(PROJECT_ROOT, "videos", "test.mp4"))
    parser.add_argument("--index", type=int, default=0, help="Webcam index")
    run(parser.parse_args())
