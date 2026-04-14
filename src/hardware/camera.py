"""
hardware/camera.py — Camera abstraction layer.

Supported sources:
  "video"     → reads frames from a video file (dev / simulation)
  "webcam"    → reads from a USB webcam via OpenCV
  "picamera2" → reads from Raspberry Pi camera via picamera2

Usage:
    from hardware.camera import create_camera

    cam = create_camera("video", path="videos/test.mp4")
    cam = create_camera("webcam")
    cam = create_camera("picamera2", width=1280, height=720)

    with cam:
        while True:
            ok, frame = cam.read()
            if not ok:
                break
"""

import cv2
import numpy as np
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

class BaseCamera(ABC):
    """Common interface for all video sources."""

    @abstractmethod
    def open(self) -> bool:
        """Open the camera. Returns True on success."""

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Read one frame. Returns (success, BGR frame)."""

    @abstractmethod
    def close(self) -> None:
        """Release all resources."""

    @property
    @abstractmethod
    def width(self) -> int: ...

    @property
    @abstractmethod
    def height(self) -> int: ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# OpenCV backend — video file or USB webcam
# ---------------------------------------------------------------------------

class CVCamera(BaseCamera):
    """Camera backed by cv2.VideoCapture (video file or USB webcam)."""

    def __init__(self, source: str | int, loop: bool = True):
        """
        source : path to .mp4/.avi  OR  webcam index (0, 1, …)
        loop   : restart video when it ends (useful during development)
        """
        self._source = source
        self._loop   = loop
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._source)
        return self._cap.isOpened()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        if not ok and self._loop and isinstance(self._source, str):
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return ok, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def width(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0

    @property
    def height(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0


# ---------------------------------------------------------------------------
# Raspberry Pi backend — picamera2
# ---------------------------------------------------------------------------

class PiCamera2Camera(BaseCamera):
    """
    Camera using picamera2 (Raspberry Pi AI Camera / v2 / v3).
    Raises ImportError on non-Pi platforms — handled by create_camera().
    """

    def __init__(self, width: int = 1280, height: int = 720):
        self._w   = width
        self._h   = height
        self._cam = None

    def open(self) -> bool:
        try:
            from picamera2 import Picamera2  # type: ignore
            self._cam = Picamera2()
            cfg = self._cam.create_preview_configuration(
                main={"size": (self._w, self._h), "format": "BGR888"}
            )
            self._cam.configure(cfg)
            self._cam.start()
            return True
        except Exception as exc:
            print(f"[PiCamera2] Failed to open: {exc}")
            return False

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cam is None:
            return False, None
        return True, self._cam.capture_array()

    def close(self) -> None:
        if self._cam is not None:
            self._cam.stop()
            self._cam = None

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_camera(source: str = "video", **kwargs) -> BaseCamera:
    """
    Create the correct camera for the current environment.

    Parameters
    ----------
    source : "video" | "webcam" | "picamera2"

    Keyword arguments
    -----------------
    video     : path (str), loop (bool=True)
    webcam    : index (int=0)
    picamera2 : width (int=1280), height (int=720)
    """
    if source == "video":
        return CVCamera(
            source=kwargs.get("path", "videos/test.mp4"),
            loop=kwargs.get("loop", True),
        )
    if source == "webcam":
        return CVCamera(source=kwargs.get("index", 0), loop=False)
    if source == "picamera2":
        return PiCamera2Camera(
            width=kwargs.get("width", 1280),
            height=kwargs.get("height", 720),
        )
    raise ValueError(
        f"Unknown source '{source}'. Use 'video', 'webcam', or 'picamera2'."
    )
