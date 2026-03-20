"""
moon_detector.py — Detector de lua refatorado
Baseado nos scripts originais (moondetector.py / moon_video_detection.py).

Melhorias em relação ao original:
  - Parâmetros configuráveis (não hardcoded)
  - Retorna um dataclass DetectionResult em vez de tuplas soltas
  - Overlay de debug opcional com todas as informações úteis
  - Tolerância a frames sem detecção (retorna resultado vazio, não exceção)
  - Fácil de tunar via DetectorConfig

Uso rápido:
    config = DetectorConfig()          # parâmetros default
    detector = MoonDetector(config)

    result = detector.detect(frame)
    if result.found:
        print(result.offset_x, result.offset_y)

    debug_frame = detector.draw_debug(frame, result)
"""

import cv2
import numpy as np
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Configuração — todos os parâmetros num único lugar
# ---------------------------------------------------------------------------

@dataclass
class DetectorConfig:
    """Parâmetros do detector. Ajuste aqui sem tocar na lógica."""

    # Pré-processamento
    blur_kernel: int = 5          # tamanho do kernel de blur (ímpar)

    # HoughCircles
    dp: float         = 1.2       # resolução acumulador (1 = mesma res. da imagem)
    min_dist: int     = 50        # distância mínima entre centros de círculos
    param1: int       = 60        # limiar alto do Canny interno
    param2: int       = 35        # limiar de votos no acumulador (menor = mais falsos positivos)
    min_radius: int   = 30        # raio mínimo em px
    max_radius: int   = 200       # raio máximo em px

    # Filtro de confiança (0.0–1.0) — não usado pelo Hough, reservado para futuras features
    min_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Resultado de uma detecção
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    found: bool       = False
    cx: int           = 0         # centro X do círculo detectado
    cy: int           = 0         # centro Y
    radius: int       = 0
    offset_x: int     = 0         # deslocamento em relação ao centro da imagem
    offset_y: int     = 0
    frame_w: int      = 0         # dimensões do frame (útil para normalizar)
    frame_h: int      = 0

    @property
    def offset_normalized(self) -> tuple[float, float]:
        """Offset como fração do tamanho do frame (-1.0 a 1.0)."""
        if self.frame_w == 0 or self.frame_h == 0:
            return 0.0, 0.0
        return self.offset_x / (self.frame_w / 2), self.offset_y / (self.frame_h / 2)

    def __repr__(self):
        if not self.found:
            return "DetectionResult(found=False)"
        nx, ny = self.offset_normalized
        return (
            f"DetectionResult(found=True, center=({self.cx},{self.cy}), "
            f"r={self.radius}, offset=({self.offset_x},{self.offset_y}), "
            f"norm=({nx:.2f},{ny:.2f}))"
        )


# ---------------------------------------------------------------------------
# Detector principal
# ---------------------------------------------------------------------------

class MoonDetector:

    def __init__(self, config: DetectorConfig | None = None):
        self.config = config or DetectorConfig()

    # ------------------------------------------------------------------
    # Detecção
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        Detecta a lua num frame BGR.
        Sempre retorna um DetectionResult (found=False se nada encontrado).
        """
        h, w = frame.shape[:2]
        center_x, center_y = w // 2, h // 2
        cfg = self.config

        # Pré-processamento
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        k = cfg.blur_kernel | 1   # garante que é ímpar
        blurred = cv2.GaussianBlur(gray, (k, k), 0)

        # Hough circles
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=cfg.dp,
            minDist=cfg.min_dist,
            param1=cfg.param1,
            param2=cfg.param2,
            minRadius=cfg.min_radius,
            maxRadius=cfg.max_radius,
        )

        if circles is None:
            return DetectionResult(found=False, frame_w=w, frame_h=h)

        # Pega apenas o círculo com mais votos (primeiro da lista)
        circles = np.round(circles[0]).astype(int)
        cx, cy, r = circles[0]

        return DetectionResult(
            found=True,
            cx=int(cx),
            cy=int(cy),
            radius=int(r),
            offset_x=int(cx) - center_x,
            offset_y=int(cy) - center_y,
            frame_w=w,
            frame_h=h,
        )

    # ------------------------------------------------------------------
    # Visualização de debug
    # ------------------------------------------------------------------

    def draw_debug(self, frame: np.ndarray, result: DetectionResult) -> np.ndarray:
        """
        Desenha overlay de debug no frame.
        Retorna uma CÓPIA do frame (não modifica o original).
        """
        out = frame.copy()
        h, w = out.shape[:2]
        cx_img, cy_img = w // 2, h // 2

        # Cruz no centro do frame
        cv2.drawMarker(out, (cx_img, cy_img), (200, 200, 0),
                       cv2.MARKER_CROSS, 20, 1, cv2.LINE_AA)

        if result.found:
            # Círculo detectado
            cv2.circle(out, (result.cx, result.cy), result.radius, (0, 220, 0), 2, cv2.LINE_AA)
            # Centro da lua
            cv2.circle(out, (result.cx, result.cy), 4, (0, 0, 255), -1)
            # Linha de offset
            cv2.line(out, (cx_img, cy_img), (result.cx, result.cy), (0, 200, 255), 1, cv2.LINE_AA)

            # Textos informativos
            nx, ny = result.offset_normalized
            lines = [
                f"centro: ({result.cx}, {result.cy})",
                f"raio  : {result.radius} px",
                f"offset: ({result.offset_x:+d}, {result.offset_y:+d}) px",
                f"norm  : ({nx:+.2f}, {ny:+.2f})",
            ]
            self._draw_info_box(out, lines, (10, 10), found=True)
        else:
            self._draw_info_box(out, ["Lua nao detectada"], (10, 10), found=False)

        return out

    @staticmethod
    def _draw_info_box(img, lines: list[str], origin: tuple[int, int], found: bool):
        """Desenha um painel de texto semi-transparente."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale, thick = 0.5, 1
        pad = 8
        line_h = 20

        text_w = max(cv2.getTextSize(l, font, scale, thick)[0][0] for l in lines)
        box_w = text_w + 2 * pad
        box_h = len(lines) * line_h + 2 * pad

        x0, y0 = origin
        overlay = img.copy()
        color_bg = (20, 80, 20) if found else (20, 20, 80)
        cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), color_bg, -1)
        cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

        for i, line in enumerate(lines):
            y = y0 + pad + (i + 1) * line_h - 4
            cv2.putText(img, line, (x0 + pad, y), font, scale, (220, 220, 220), thick, cv2.LINE_AA)
