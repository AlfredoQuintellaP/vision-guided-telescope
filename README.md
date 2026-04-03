# Vision-Guided Telescope

A Raspberry Pi telescope mount that uses computer vision to lock onto and
track the moon in real time.  A PID controller converts the detected
pixel offset into stepper-motor commands, keeping the moon centred in the
frame as it drifts.

---

## Project structure

```
telescope/
├── config/
│   ├── __init__.py
│   └── settings.py          ← ALL tunable parameters in one place
├── src/
│   ├── detection/
│   │   └── moon_detector.py ← HoughCircles + brightness-based selection
│   ├── control/
│   │   └── pid.py           ← PID controller (single axis)
│   ├── hardware/
│   │   ├── camera.py        ← video file / webcam / picamera2 abstraction
│   │   └── motor.py         ← 28BYJ-48 stepper via ULN2003
│   └── utils/
│       └── overlay.py       ← OpenCV HUD drawing helpers
├── scripts/
│   ├── main.py              ← entry point (simulate + live modes)
│   └── tune_detector.py     ← interactive slider tuner for detector params
├── tests/
│   └── test_detector.py
├── videos/
│   └── test.mp4
└── requirements.txt
```

---

## Quick start

### 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### 2 — Run the simulation (no hardware needed)

```bash
python scripts/main.py
# or explicitly:
python scripts/main.py --mode simulate --path videos/test.mp4
```

Keyboard shortcuts while the window is open:

| Key       | Action                     |
|-----------|----------------------------|
| `SPACE`   | Pause / resume             |
| `R`       | Restart video              |
| `Q`/`ESC` | Quit                       |

### 3 — Tune the detector

```bash
python scripts/tune_detector.py
```

Adjust the sliders live.  When you find good values, copy them into
`config/settings.py` → `DetectorSettings`.  The tuner prints the final
values as ready-to-paste Python when you close it.

### 4 — Run on Raspberry Pi (live mode)

```bash
python scripts/main.py --mode live
```

---

## Detection parameters (config/settings.py)

The moon detector uses `cv2.HoughCircles`.  The two most important parameters:

| Parameter    | Default | Effect |
|---|---|---|
| `param2`     | **40**  | Accumulator vote threshold. **Lower = more detections, more false positives.** The original value of 35 caused 10–35 false circles per frame. 40 eliminates false positives while keeping real detections. |
| `param1`     | 100     | Upper Canny threshold. Lower values let noise edges through. |
| `blur_kernel`| 7       | Pre-blur size. Larger removes more noise; too large blurs moon edge. |

Additionally, `use_brightness_selection = True` makes the detector pick
the candidate with the highest interior brightness when multiple circles
are found — the moon is always the brightest object in a telescope frame.

---

## PID tuning (config/settings.py → PIDSettings)

Start with the default gains and observe the ghost crosshair in simulate
mode:

- **Ghost converges too slowly** → increase `kp`
- **Ghost oscillates** → decrease `kp` or increase `kd`
- **Steady-state error remains** → increase `ki` slightly
- **Jitter near centre** → increase `deadband`

---

## Hardware — 28BYJ-48 + ULN2003

Default GPIO wiring (BCM):

```
Azimuth  : IN1=GPIO2  IN2=GPIO3  IN3=GPIO14  IN4=GPIO22
Elevation: IN1=GPIO6  IN2=GPIO13 IN3=GPIO19  IN4=GPIO26
```

Override in `config/settings.py` → `MotorSettings` if your wiring differs.

---

## Running tests

```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_detector.py
```
