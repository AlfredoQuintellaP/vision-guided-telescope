"""
camera.py — Abstração de câmera
  - PC / dev  : lê frames de um ficheiro de vídeo (ou webcam USB)
  - Raspberry : usa picamera2 com a AI Camera

Uso:
    cam = Camera.create(source="video", path="videos/test.mp4")
    cam = Camera.create(source="webcam")
    cam = Camera.create(source="picamera2")   # apenas na Raspberry

    with cam:
        while True:
            ok, frame = cam.read()
            if not ok:
                break
"""

import cv2
import numpy as np
from abc import ABC, abstractmethod


class BaseCamera(ABC):
    """Interface comum para todas as fontes de vídeo."""

    @abstractmethod
    def open(self) -> bool:
        """Abre a câmera. Retorna True se OK."""

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Lê um frame. Retorna (sucesso, frame BGR)."""

    @abstractmethod
    def close(self):
        """Libera recursos."""

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
# Implementação PC — arquivo de vídeo ou webcam USB
# ---------------------------------------------------------------------------

class CVCamera(BaseCamera):
    """Câmera baseada em OpenCV (vídeo ou webcam USB)."""

    def __init__(self, source: str | int, loop: bool = True):
        """
        source : caminho para .mp4 / .avi  OU  índice de webcam (0, 1, ...)
        loop   : ao chegar no fim do vídeo, recomeça (útil no dev)
        """
        self._source = source
        self._loop = loop
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._source)
        return self._cap.isOpened()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None

        ok, frame = self._cap.read()

        if not ok and self._loop and isinstance(self._source, str):
            # reinicia o vídeo
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()

        return ok, frame

    def close(self):
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
# Implementação Raspberry — picamera2 + AI Camera
# ---------------------------------------------------------------------------

class PiCamera2Camera(BaseCamera):
    """
    Câmera usando picamera2 (Raspberry Pi AI Camera / v2 / v3).
    Esta classe só funciona na Raspberry. No PC levanta ImportError.
    """

    def __init__(self, width: int = 1280, height: int = 720):
        self._w = width
        self._h = height
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
        except Exception as e:
            print(f"[PiCamera2] Erro ao abrir: {e}")
            return False

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cam is None:
            return False, None
        frame = self._cam.capture_array()
        return True, frame

    def close(self):
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
    Factory para criar a câmera certa conforme o ambiente.

    Parâmetros:
        source    : "video"     → CVCamera com ficheiro de vídeo
                    "webcam"    → CVCamera com índice de webcam
                    "picamera2" → PiCamera2Camera (só Raspberry)

    Kwargs para "video":
        path (str)  : caminho do vídeo  (default: "videos/test.mp4")
        loop (bool) : reiniciar no fim  (default: True)

    Kwargs para "webcam":
        index (int) : índice da câmera  (default: 0)

    Kwargs para "picamera2":
        width  (int) : largura  (default: 1280)
        height (int) : altura   (default: 720)
    """
    if source == "video":
        path = kwargs.get("path", "videos/test.mp4")
        loop = kwargs.get("loop", True)
        return CVCamera(source=path, loop=loop)

    elif source == "webcam":
        index = kwargs.get("index", 0)
        return CVCamera(source=index, loop=False)

    elif source == "picamera2":
        w = kwargs.get("width", 1280)
        h = kwargs.get("height", 720)
        return PiCamera2Camera(width=w, height=h)

    else:
        raise ValueError(f"source desconhecido: '{source}'. Use 'video', 'webcam' ou 'picamera2'.")
