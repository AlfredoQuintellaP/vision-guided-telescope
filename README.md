# PIE 4 — Telescope Automation

## Project structure

```
telescope/
├── src/
│   ├── camera.py          ← camera abstraction layer (PC ↔ Raspberry Pi)
│   ├── moon_detector.py   ← moon detector (refactored HoughCircles)
│   └── run_detector.py    ← dev script with live parameter sliders
├── videos/
│   └── test.mp4           ← test video (used on PC)
└── requirements.txt
```

---

## Setup on PC

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Setup on Raspberry Pi

`picamera2` is a system package and cannot be installed via pip. The venv must be created with `--system-site-packages` so it can see it:

```bash
sudo apt update
sudo apt install -y python3-picamera2

python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install opencv-python numpy
```

To verify everything is working:
```bash
python3 -c "import picamera2; print('picamera2 OK')"
rpicam-hello --list-cameras   # should list your camera
```

---

## Running the detector

**On PC** — uses the test video by default:
```bash
source venv/bin/activate
python src/run_detector.py
python src/run_detector.py --source video --path videos/test.mp4  # explicit
python src/run_detector.py --source webcam                         # webcam
```

**On Raspberry Pi** — uses the AI Camera:
```bash
source venv/bin/activate
python src/run_detector.py --source picamera2
```

Two windows will open: the video feed with the detection overlay, and a sliders panel.
Tune the parameters until detection is stable, then note down the values.

### Keyboard shortcuts
| Key | Action |
|-----|--------|
| `SPACE` | Pause / resume |
| `R` | Restart the video |
| `S` | Save current frame as `.png` |
| `Q` / `ESC` | Quit |

---

## Detector parameters

All parameters live in `DetectorConfig` inside `moon_detector.py`:

| Parameter | Effect | Default |
|-----------|--------|---------|
| `blur_kernel` | Smooths noise. Higher → less noise, less detail | 5 |
| `param1` | Canny edge threshold. Higher → requires stronger edges | 60 |
| `param2` | Hough sensitivity. Lower → detects more circles (including false positives) | 35 |
| `min_radius` | Minimum moon radius in px | 30 |
| `max_radius` | Maximum moon radius in px | 200 |
| `min_dist` | Minimum distance between detected circle centres | 50 |

---

## Next steps (to implement)

- [ ] `motor.py` — motor abstraction (MockMotor on PC / StepperMotor on RPi)
- [ ] `pid.py` — PID controller for position servo loop
- [ ] `main.py` — main loop: capture → detect → PID → command motor
- [ ] Tune detector parameters with the real camera

---

## Switching between PC and Raspberry Pi

Only one line changes — the camera source passed to `create_camera()`:

```python
# PC — video file
cam = create_camera(source="video", path="videos/test.mp4")

# Raspberry Pi AI Camera (imx500)
cam = create_camera(source="picamera2", width=1280, height=720)
```

Everything else (detector, PID, motor control) stays the same.
