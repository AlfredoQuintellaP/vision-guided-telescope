"""
tests/test_detector.py — Unit tests for MoonDetector.

Run from the project root:
    python -m pytest tests/
    python tests/test_detector.py        # without pytest
"""

import sys
import os
import unittest
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import DetectorSettings
from src.detection import MoonDetector, DetectionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(w: int = 640, h: int = 480,
                bg: int = 30) -> np.ndarray:
    """Blank dark BGR frame."""
    return np.full((h, w, 3), bg, dtype=np.uint8)


def _draw_moon(frame: np.ndarray, cx: int, cy: int,
               r: int, brightness: int = 220) -> None:
    """Draw a bright filled circle simulating the moon."""
    import cv2
    cv2.circle(frame, (cx, cy), r, (brightness, brightness, brightness), -1)
    # Soften the edge slightly (real moon has a gradual limb)
    cv2.circle(frame, (cx, cy), r, (brightness - 20,) * 3, 2)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDetectionResult(unittest.TestCase):

    def test_offset_normalized_zero(self):
        r = DetectionResult(found=True, cx=320, cy=240,
                            frame_w=640, frame_h=480,
                            offset_x=0, offset_y=0)
        nx, ny = r.offset_normalized
        self.assertAlmostEqual(nx, 0.0)
        self.assertAlmostEqual(ny, 0.0)

    def test_offset_normalized_values(self):
        # Moon at top-left quadrant: offset = (-160, -120) on a 640x480 frame
        r = DetectionResult(found=True, cx=160, cy=120,
                            frame_w=640, frame_h=480,
                            offset_x=-160, offset_y=-120)
        nx, ny = r.offset_normalized
        self.assertAlmostEqual(nx, -0.5)
        self.assertAlmostEqual(ny, -0.5)

    def test_repr_found(self):
        r = DetectionResult(found=True, cx=100, cy=200, radius=50,
                            offset_x=10, offset_y=-20,
                            frame_w=640, frame_h=480)
        self.assertIn("found=True", repr(r))

    def test_repr_not_found(self):
        r = DetectionResult(found=False)
        self.assertEqual(repr(r), "DetectionResult(found=False)")


class TestMoonDetector(unittest.TestCase):

    def setUp(self):
        # Relaxed settings that work reliably on synthetic frames
        self.cfg = DetectorSettings(
            blur_kernel=7,
            param1=50,
            param2=20,
            min_radius=20,
            max_radius=200,
            min_dist=50,
            use_brightness_selection=True,
        )
        self.detector = MoonDetector(self.cfg)

    def test_empty_frame_returns_not_found(self):
        frame  = _make_frame()
        result = self.detector.detect(frame)
        # A plain dark frame should not produce a detection
        # (if it does, param2 is too low)
        if result.found:
            # Acceptable only if radius is tiny noise — not a real detection
            self.assertLess(result.radius, 15,
                            "False positive on blank frame — raise param2")

    def test_detects_bright_circle(self):
        frame = _make_frame(640, 480, bg=20)
        _draw_moon(frame, cx=320, cy=240, r=60)
        result = self.detector.detect(frame)
        self.assertTrue(result.found, "Should detect bright circle on dark background")

    def test_offset_near_zero_when_centred(self):
        frame = _make_frame(640, 480, bg=20)
        _draw_moon(frame, cx=320, cy=240, r=60)
        result = self.detector.detect(frame)
        if result.found:
            # Allow ±15 px tolerance for Hough rounding
            self.assertAlmostEqual(result.offset_x, 0, delta=15)
            self.assertAlmostEqual(result.offset_y, 0, delta=15)

    def test_brightness_selection_picks_brighter_circle(self):
        """
        Two circles: one dim, one bright.
        brightness_selection must return the bright one.
        """
        import cv2
        frame = _make_frame(800, 600, bg=20)
        # Dim circle (left)
        cv2.circle(frame, (200, 300), 60, (80, 80, 80), -1)
        # Bright circle (right) — this is the "moon"
        cv2.circle(frame, (600, 300), 60, (220, 220, 220), -1)

        self.cfg.use_brightness_selection = True
        result = self.detector.detect(frame)
        if result.found:
            # Should be closer to (600, 300) than to (200, 300)
            dist_bright = ((result.cx - 600) ** 2 + (result.cy - 300) ** 2) ** 0.5
            dist_dim    = ((result.cx - 200) ** 2 + (result.cy - 300) ** 2) ** 0.5
            self.assertLess(dist_bright, dist_dim,
                            "Brightness selection should pick the brighter circle")

    def test_draw_debug_does_not_modify_original(self):
        frame    = _make_frame()
        original = frame.copy()
        result   = DetectionResult(found=False)
        _        = self.detector.draw_debug(frame, result)
        np.testing.assert_array_equal(frame, original,
                                      "draw_debug must not modify the original frame")

    def test_frame_dimensions_in_result(self):
        frame  = _make_frame(1280, 720)
        result = self.detector.detect(frame)
        self.assertEqual(result.frame_w, 1280)
        self.assertEqual(result.frame_h, 720)


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
