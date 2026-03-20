# PIE 4 — Automatisation d'un télescope

## Estrutura do projeto

```
telescope/
├── src/
│   ├── camera.py          ← abstração de câmera (PC ↔ Raspberry)
│   ├── moon_detector.py   ← detector de lua (HoughCircles refatorado)
│   └── run_detector.py    ← script de dev com sliders em tempo real
├── videos/
│   └── test.mp4           ← vídeo de teste
└── requirements.txt
```

---

## Setup no PC

```bash
pip install -r requirements.txt
```

---

## Rodar o detector (PC)

```bash
cd telescope

# Com o vídeo de teste (padrão)
python src/run_detector.py

# Com webcam
python src/run_detector.py --source webcam

# Com outro vídeo
python src/run_detector.py --source video --path videos/outro.mp4
```

Uma janela de vídeo e uma janela de sliders vão abrir.  
Ajuste os parâmetros até a lua ser detectada de forma estável e anote os valores.

### Atalhos
| Tecla | Ação |
|-------|------|
| `ESPAÇO` | Pausa / retoma |
| `R` | Reinicia o vídeo |
| `S` | Salva o frame atual como `.png` |
| `Q` / `ESC` | Sai |

---

## Parâmetros do detector

Todos em `DetectorConfig` dentro de `moon_detector.py`:

| Parâmetro | Efeito | Valor inicial |
|-----------|--------|---------------|
| `blur_kernel` | Suaviza ruído. Maior → menos ruído, menos detalhe | 5 |
| `param1` | Limiar Canny (bordas). Maior → exige bordas mais fortes | 60 |
| `param2` | Sensibilidade Hough. Menor → detecta mais círculos (inclusive falsos) | 35 |
| `min_radius` | Raio mínimo da lua em px | 30 |
| `max_radius` | Raio máximo da lua em px | 200 |
| `min_dist` | Distância mínima entre círculos detectados | 50 |

---

## Próximas etapas (a implementar)

- [ ] `motor.py` — abstração de motor (MockMotor PC / StepperMotor RPi)
- [ ] `pid.py` — controlador PID para asservissement de posição
- [ ] `main.py` — loop principal: captura → detecta → PID → comanda motor
- [ ] Migrar para Raspberry + testar com câmera real

---

## Migrar para Raspberry

Apenas trocar a linha de criação da câmera:

```python
# PC
cam = create_camera(source="video", path="videos/test.mp4")

# Raspberry Pi AI Camera
cam = create_camera(source="picamera2", width=1280, height=720)
```

O resto do código não muda.
