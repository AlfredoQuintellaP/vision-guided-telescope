# PIE 4 — Telescope Automation

## Project structure

```
telescope/
├── src/
│   ├── camera.py          ← camera abstraction layer (PC ↔ Raspberry)
│   ├── moon_detector.py   ← moon detector (refactored HoughCircles)
│   └── run_detector.py    ← dev script with live parameter sliders
├── videos/
│   └── test.mp4           ← test video
└── requirements.txt
```

---

## Setup on PC

```bash
pip install -r requirements.txt
```

---

## Running the detector (PC)

```bash
cd telescope

# Using the test video (default)
python src/run_detector.py

# Using a webcam
python src/run_detector.py --source webcam

# Using a different video file
python src/run_detector.py --source video --path videos/other.mp4
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
- [ ] Deploy to Raspberry Pi and test with the real camera

---

## Deploying to Raspberry Pi

Only one line needs to change — the camera source:

```python
# PC
cam = create_camera(source="video", path="videos/test.mp4")

# Raspberry Pi AI Camera
cam = create_camera(source="picamera2", width=1280, height=720)
```

Everything else stays the same.
