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
│   │   └── motor.py         ← STEP/DIR stepper driver (A4988 / DRV8825)
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

## Hardware — STEP/DIR stepper motors (A4988 / DRV8825)

The mount uses two stepper motors controlled by STEP/DIR driver boards
(A4988, DRV8825, or compatible).  Each axis requires only two GPIO pins:
**DIR** sets the rotation direction and **STEP** advances the motor one
step per pulse.

### GPIO wiring (BCM numbering)

```
Azimuth   : DIR=GPIO26   STEP=GPIO19
Elevation : DIR=GPIO21   STEP=GPIO20
```

Override in `config/settings.py` → `MotorSettings` if your wiring differs.

### Driver board setup

| MS pin config | Steps/rev (1.8° motor) | Use case |
|---|---|---|
| Full step      | 200   | Fast slew, low torque smoothness |
| Half step      | 400   | Good balance                     |
| 1/16 step      | 3200  | Quiet, precise tracking          |

Set `STEPS_PER_REVOLUTION` in `motor.py` (or `MotorSettings`) to match
your chosen microstepping factor.  Tracking accuracy depends on this
value being correct.

### VREF / current limit

Before connecting motors, set the VREF trim-pot on each driver board to
limit current to your motor's rated value (check the datasheet).
Exceeding the rated current will overheat the driver and motor.

### Wiring diagram (per axis)

```
Raspberry Pi              Driver board           Stepper motor
──────────────            ────────────           ─────────────
GPIO 26 (DIR)  ────────►  DIR
GPIO 19 (STEP) ────────►  STEP
GND            ────────►  GND
3.3 V          ────────►  LOGIC VCC
                          VMOT  ◄──── 12 V supply
                          GND   ◄──── 12 V GND
                          1A/1B/2A/2B ──────────► Motor coils
```

> **Note:** VMOT and logic VCC share a common GND.  Always connect GND
> before powering VMOT to avoid latch-up on the driver IC.

---

## Running tests
```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_detector.py
```
