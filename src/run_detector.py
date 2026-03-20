"""
run_detector.py — Script de desenvolvimento para tunar o detector

Abre uma janela OpenCV com:
  - Vídeo com overlay de detecção
  - Sliders para ajustar todos os parâmetros do Hough em tempo real
  - Log de resultados no terminal

Controles:
  ESPAÇO  → pausa / retoma
  R       → reinicia o vídeo
  S       → salva o frame atual em debug_frame.png
  Q / ESC → sai

Uso:
    python run_detector.py
    python run_detector.py --source video --path videos/test.mp4
    python run_detector.py --source webcam
"""

import argparse
import cv2
import sys
import os

# Adiciona src/ ao path para permitir rodar de qualquer pasta
sys.path.insert(0, os.path.dirname(__file__))

from camera import create_camera
from moon_detector import DetectorConfig, MoonDetector


# ---------------------------------------------------------------------------
# Sliders (trackbars) — mapeamento nome → (min, max, default)
# ---------------------------------------------------------------------------

SLIDERS = {
    "blur_kernel": (1, 21,  5),
    "param1":      (10, 300, 60),
    "param2":      (5,  100, 35),
    "min_radius":  (5,  300, 30),
    "max_radius":  (10, 600, 200),
    "min_dist":    (5,  300, 50),
}

WINDOW = "Telescope — Moon Detector (Q para sair)"
CTRL   = "Parametros"


def make_nothing(_): pass   # callback vazio para createTrackbar


def build_windows():
    cv2.namedWindow(WINDOW,  cv2.WINDOW_NORMAL)
    cv2.namedWindow(CTRL,    cv2.WINDOW_NORMAL)
    cv2.resizeWindow(CTRL, 500, 220)

    for name, (lo, hi, default) in SLIDERS.items():
        cv2.createTrackbar(name, CTRL, default, hi, make_nothing)
        cv2.setTrackbarMin(name, CTRL, lo)


def read_config_from_sliders() -> DetectorConfig:
    cfg = DetectorConfig()
    for name in SLIDERS:
        val = cv2.getTrackbarPos(name, CTRL)
        setattr(cfg, name, val)
    # blur_kernel deve ser ímpar
    cfg.blur_kernel = max(1, cfg.blur_kernel | 1)
    return cfg


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run(args):
    cam = create_camera(
        source=args.source,
        path=getattr(args, "path", "videos/test.mp4"),
        index=getattr(args, "index", 0),
    )

    if not cam.open():
        print("[ERRO] Não foi possível abrir a câmera.")
        return

    build_windows()

    detector = MoonDetector()
    paused = False
    frame_count = 0
    last_frame = None

    print("Detector iniciado. Ajuste os sliders na janela 'Parametros'.")
    print("Atalhos: ESPAÇO=pause  R=reinicia  S=salva frame  Q/ESC=sai\n")

    while True:
        if not paused:
            ok, frame = cam.read()
            if not ok:
                print("Fim do vídeo.")
                break
            last_frame = frame
            frame_count += 1
        else:
            frame = last_frame

        # Recria o detector com os parâmetros atuais dos sliders
        detector.config = read_config_from_sliders()

        result = detector.detect(frame)
        debug = detector.draw_debug(frame, result)

        # FPS / frame counter no canto
        cv2.putText(debug, f"frame {frame_count}", (debug.shape[1] - 120, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)
        if paused:
            cv2.putText(debug, "PAUSADO", (debug.shape[1] // 2 - 40, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        cv2.imshow(WINDOW, debug)

        # Log no terminal a cada 30 frames (para não spammar)
        if frame_count % 30 == 0:
            print(f"[f{frame_count:04d}] {result}")

        key = cv2.waitKey(25) & 0xFF

        if key in (ord('q'), 27):     # Q ou ESC
            break
        elif key == ord(' '):         # Espaço
            paused = not paused
        elif key == ord('r'):         # Reinicia vídeo
            cam.close()
            cam.open()
            frame_count = 0
            print("Vídeo reiniciado.")
        elif key == ord('s') and last_frame is not None:
            fname = f"debug_frame_{frame_count:04d}.png"
            cv2.imwrite(fname, debug)
            print(f"Frame salvo: {fname}")

    cam.close()
    cv2.destroyAllWindows()
    print("Encerrado.")


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DEFAULT_VIDEO_PATH = os.path.join(PROJECT_ROOT, "videos", "test.mp4")

    parser = argparse.ArgumentParser(description="Tuner do detector de lua")

    parser.add_argument(
        "--source",
        default="video",
        choices=["video", "webcam", "picamera2"]
    )

    parser.add_argument(
        "--path",
        default=DEFAULT_VIDEO_PATH
    )

    parser.add_argument(
        "--index",
        type=int,
        default=0
    )

    args = parser.parse_args()
    run(args)
