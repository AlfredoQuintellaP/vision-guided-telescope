"""
utils/overlay.py — OpenCV drawing helpers for the telescope HUD.

All functions draw directly onto *img* in-place (pass a .copy() if
you need to preserve the original).
"""

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def draw_crosshair(
    img: np.ndarray,
    x: int, y: int,
    color: tuple[int, int, int],
    size: int = 14,
    thickness: int = 1,
) -> None:
    cv2.line(img, (x - size, y), (x + size, y), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x, y - size), (x, y + size), color, thickness, cv2.LINE_AA)


def draw_arrow(
    img: np.ndarray,
    x0: int, y0: int,
    x1: int, y1: int,
    color: tuple[int, int, int],
    thickness: int = 1,
) -> None:
    cv2.arrowedLine(img, (x0, y0), (x1, y1), color, thickness,
                    cv2.LINE_AA, tipLength=0.2)


# ---------------------------------------------------------------------------
# Info panel
# ---------------------------------------------------------------------------

def draw_panel(
    img: np.ndarray,
    lines: list[tuple[str, str]],
    x: int,
    y: int,
    width: int = 310,
) -> None:
    """
    Semi-transparent info panel.

    lines : list of (label, value) string pairs
    """
    font       = cv2.FONT_HERSHEY_SIMPLEX
    scale, thick = 0.45, 1
    lh         = 19
    pad        = 8
    h          = len(lines) * lh + 2 * pad

    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + width, y + h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

    for i, (label, value) in enumerate(lines):
        yy = y + pad + (i + 1) * lh - 4
        cv2.putText(img, label, (x + pad, yy),
                    font, scale, (160, 160, 160), thick, cv2.LINE_AA)
        cv2.putText(img, value, (x + pad + 160, yy),
                    font, scale, (230, 230, 230), thick, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Error bars
# ---------------------------------------------------------------------------

def draw_error_bars(
    img: np.ndarray,
    offset_x: int,
    offset_y: int,
) -> None:
    """
    Draw horizontal X-error bar at the bottom and vertical Y-error bar
    on the right side of the frame.
    """
    h, w = img.shape[:2]
    bar_h = 18

    # X error (horizontal bar at bottom centre)
    half  = w // 2
    ex    = int(offset_x * 0.3)
    bar_y = h - bar_h - 6
    cv2.rectangle(img,
                  (half, bar_y),
                  (half + ex, bar_y + bar_h // 2 - 1),
                  (0, 180, 255), -1)

    # Y error (vertical bar on right edge)
    ey = int(offset_y * 0.3)
    bx = w - 18
    cv2.rectangle(img,
                  (bx, h // 2),
                  (bx + bar_h // 2 - 1, h // 2 + ey),
                  (0, 255, 180), -1)


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------

LEGEND_ENTRIES = [
    ((0, 210, 0),   "Green",  "real moon"),
    ((220, 100, 0), "Blue",   "ghost (PID corrected)"),
    ((0, 0, 220),   "Red",    "target centre"),
    ((0, 200, 255), "Cyan",   "PID correction arrow"),
]


def draw_legend(img: np.ndarray) -> None:
    """Draw colour legend in the bottom-left corner."""
    h = img.shape[0]
    for i, (col, lbl, txt) in enumerate(LEGEND_ENTRIES):
        lx = 8
        ly = h - 90 + i * 18
        cv2.rectangle(img, (lx, ly), (lx + 12, ly + 10), col, -1)
        cv2.putText(img, f"{lbl}: {txt}", (lx + 18, ly + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
