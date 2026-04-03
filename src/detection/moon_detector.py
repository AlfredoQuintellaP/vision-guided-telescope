"""
detection/moon_detector.py — Moon detector using Hough Circle Transform.

Key improvements over original:
  - Parameters driven by DetectorSettings (from config/settings.py), not hardcoded.
  - Brightness-based candidate selection: when multiple circles pass the Hough
    filter, the one with the highest mean interior brightness is returned.
    The moon is always the brightest near-circular object in a telescope frame,
    so this eliminates the false positives that plagued the old param2=35 setting.
  - Returns a typed DetectionResult dataclass (no loose tuples).
  - draw_debug() for overlay visualisation; does not modify the original frame.
"""

import cv2
import numpy as np
from dataclasses import dataclass

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import DetectorSettings


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    found:    bool = False
    cx:       int  = 0      # moon centre X (pixels)
    cy:       int  = 0      # moon centre Y (pixels)
    radius:   int  = 0
    offset_x: int  = 0      # cx - frame_centre_x
    offset_y: int  = 0      # cy - frame_centre_y
    frame_w:  int  = 0
    frame_h:  int  = 0

    @property
    def offset_normalized(self) -> tuple[float, float]:
        """Offset as fraction of half-frame size  (–1.0 … +1.0)."""
        if self.frame_w == 0 or self.frame_h == 0:
            return 0.0, 0.0
        return (self.offset_x / (self.frame_w / 2),
                self.offset_y / (self.frame_h / 2))

    def __repr__(self) -> str:
        if not self.found:
            return "DetectionResult(found=False)"
        nx, ny = self.offset_normalized
        return (f"DetectionResult(found=True, center=({self.cx},{self.cy}), "
                f"r={self.radius}, offset=({self.offset_x:+d},{self.offset_y:+d}), "
                f"norm=({nx:+.2f},{ny:+.2f}))")


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class MoonDetector:
    """
    Detects the moon in a BGR frame using cv2.HoughCircles.

    Usage:
        detector = MoonDetector()              # uses CFG.detector defaults
        detector = MoonDetector(my_settings)   # custom DetectorSettings

        result = detector.detect(frame)
        if result.found:
            print(result.offset_x, result.offset_y)
    """

    def __init__(self, settings: DetectorSettings | None = None):
        if settings is None:
            from config import CFG
            settings = CFG.detector
        self.settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        Detect the moon in a BGR frame.
        Always returns a DetectionResult; found=False if nothing detected.
        """
        h, w = frame.shape[:2]
        cfg = self.settings

        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        k       = max(1, cfg.blur_kernel) | 1          # ensure odd
        blurred = cv2.GaussianBlur(gray, (k, k), cfg.blur_sigma)

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp       = cfg.dp,
            minDist  = cfg.min_dist,
            param1   = cfg.param1,
            param2   = cfg.param2,
            minRadius= cfg.min_radius,
            maxRadius= cfg.max_radius,
        )

        if circles is None:
            return DetectionResult(found=False, frame_w=w, frame_h=h)

        circles = np.round(circles[0]).astype(int)

        # Candidate selection: pick the circle with the highest interior brightness.
        # This is the single most effective guard against false positives because
        # the moon is always the brightest near-circular object in the frame.
        if cfg.use_brightness_selection and len(circles) > 1:
            best_cx, best_cy, best_r = self._brightest_circle(gray, circles)
        else:
            best_cx, best_cy, best_r = circles[0]

        cx_img, cy_img = w // 2, h // 2
        return DetectionResult(
            found    = True,
            cx       = int(best_cx),
            cy       = int(best_cy),
            radius   = int(best_r),
            offset_x = int(best_cx) - cx_img,
            offset_y = int(best_cy) - cy_img,
            frame_w  = w,
            frame_h  = h,
        )

    # ------------------------------------------------------------------
    # Debug visualisation
    # ------------------------------------------------------------------

    def draw_debug(self, frame: np.ndarray, result: DetectionResult) -> np.ndarray:
        """
        Returns a copy of the frame with a detection overlay drawn on it.
        The original frame is never modified.
        """
        out = frame.copy()
        h, w = out.shape[:2]
        cx_img, cy_img = w // 2, h // 2

        # Frame centre marker
        cv2.drawMarker(out, (cx_img, cy_img), (200, 200, 0),
                       cv2.MARKER_CROSS, 20, 1, cv2.LINE_AA)

        if result.found:
            cv2.circle(out, (result.cx, result.cy), result.radius,
                       (0, 220, 0), 2, cv2.LINE_AA)
            cv2.circle(out, (result.cx, result.cy), 4, (0, 0, 255), -1)
            cv2.line(out, (cx_img, cy_img), (result.cx, result.cy),
                     (0, 200, 255), 1, cv2.LINE_AA)

            nx, ny = result.offset_normalized
            self._draw_info_box(out, [
                f"centre : ({result.cx}, {result.cy})",
                f"radius : {result.radius} px",
                f"offset : ({result.offset_x:+d}, {result.offset_y:+d}) px",
                f"norm   : ({nx:+.2f}, {ny:+.2f})",
            ], (10, 10), found=True)
        else:
            self._draw_info_box(out, ["Moon not detected"], (10, 10), found=False)

        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _brightest_circle(
        gray: np.ndarray,
        circles: np.ndarray,
    ) -> tuple[int, int, int]:
        """
        Return the (cx, cy, r) of the circle whose interior has the highest
        mean pixel brightness in *gray*.
        """
        best_score = -1.0
        best = circles[0]
        mask = np.zeros_like(gray)
        for cx, cy, r in circles:
            mask[:] = 0
            cv2.circle(mask, (cx, cy), int(r), 255, -1)
            score = float(cv2.mean(gray, mask=mask)[0])
            if score > best_score:
                best_score = score
                best = (cx, cy, r)
        return best

    @staticmethod
    def _draw_info_box(img: np.ndarray, lines: list[str],
                       origin: tuple[int, int], found: bool) -> None:
        font   = cv2.FONT_HERSHEY_SIMPLEX
        scale  = 0.5
        thick  = 1
        pad    = 8
        line_h = 20

        text_w  = max(cv2.getTextSize(l, font, scale, thick)[0][0] for l in lines)
        box_w   = text_w + 2 * pad
        box_h   = len(lines) * line_h + 2 * pad
        x0, y0  = origin

        overlay  = img.copy()
        bg_color = (20, 80, 20) if found else (20, 20, 80)
        cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), bg_color, -1)
        cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

        for i, line in enumerate(lines):
            y = y0 + pad + (i + 1) * line_h - 4
            cv2.putText(img, line, (x0 + pad, y),
                        font, scale, (220, 220, 220), thick, cv2.LINE_AA)
