# AI-Enabled Fire/Smoke Detection and Automated Emergency Response System

Deep-learning + IoT prototype that detects visible **fire** and **smoke** in camera streams, confirms events with
temporal logic and optional sensor fusion, stores evidence, raises alerts and drives safe low-voltage prototype
responses, with a live web dashboard. Academic prototype — **not** a certified life-safety product.

```
Camera → Dataset → YOLO detector → Real-time inference → Decision engine → IoT verification → Alerts / prototype response → Dashboard
```

## Phase-2 modules (this repo)

| Module | What it does | Where |
|---|---|---|
| **1. AI fire/smoke detection model** | Stratified dataset build from two public sets (indoor + outdoor), YOLO11n training on CPU, held-out evaluation (precision / recall / F1 / mAP per class, FP/FN analysis, latency) | `training/`, `dataset/`, `models/`, `configs/data.yaml` |
| **2. Real-time inference + decision engine + event log** | Webcam/video/RTSP pipeline with overlays, temporal NORMAL → WARNING → CONFIRMED → RECOVERY state machine with hysteresis and sensor fusion, evidence snapshots, FastAPI + SQLite backend with the required API, live dashboard, software buzzer, notifications, ESP32 sensor simulator | `inference/`, `vision/`, `decision_engine/`, `backend/`, `dashboard/`, `notifications/`, `iot/` |

## Quick start (any laptop, no GPU needed)

Requirements: Python 3.10+ (3.13 tested), a webcam (optional — sample images/videos work too), ~3 GB disk for packages.

**Windows**
```bat
git clone https://github.com/bhatspranav7/AI-Enabled-fire-Smoke-detection-systeem-using-Deep-learning-Emergency-Monitoring.git
cd AI-Enabled-fire-Smoke-detection-systeem-using-Deep-learning-Emergency-Monitoring
setup.bat
run_demo.bat
```

**Linux / macOS**
```bash
git clone https://github.com/bhatspranav7/AI-Enabled-fire-Smoke-detection-systeem-using-Deep-learning-Emergency-Monitoring.git
cd AI-Enabled-fire-Smoke-detection-systeem-using-Deep-learning-Emergency-Monitoring
chmod +x setup.sh run_demo.sh && ./setup.sh
./run_demo.sh
```

`run_demo` opens three processes — backend + dashboard (http://127.0.0.1:8000), ESP32 sensor simulator, live
inference window — and the dashboard in your browser. The trained model `models/best.pt` is committed, so no
dataset download or training is needed to run the demo.

No webcam / no real fire? Cycle through bundled sample frames or a video:
```bat
run_demo.bat demo_media\images
run_demo.bat path\to\fire_video.mp4
```

### Manual start (three terminals)
```bash
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000     # 1. backend + dashboard  (http://127.0.0.1:8000, API docs at /docs)
python iot/sensor_simulator.py                                     # 2. fake ESP32: keys n/s/h/b/x = normal/smoke/heat/both/disconnect
python inference/run_live.py [--source 0 | video.mp4 | folder]     # 3. live detection: keys q quit, a ack, e e-stop, s snapshot, r reset
```

See **[DEMO.md](DEMO.md)** for the full demonstration script (scenarios, what to say, what to show).

## Module 1 — AI model

| Item | Value |
|---|---|
| Detector | Ultralytics **YOLO11n** (lightweight baseline per PDF §5.2), pretrained COCO checkpoint fine-tuned |
| Classes | `0 = fire`, `1 = smoke` (steam / dust / fog handled as hard negatives) |
| Data | 3,000 train / 600 val / 600 test images, stratified fire-only / smoke-only / both / negative, drawn from two public YOLO-format sets: [fog_fire_detection (40.9k, CC-BY-4.0, mostly outdoor + CCTV)](https://huggingface.co/datasets/jojomoi-meme/fog_fire_detection) and [ISFire-4 (7.4k, MIT, indoor)](https://huggingface.co/datasets/shahriar-5/ISFire-4). Full register: [`dataset/DATASET_REGISTER.md`](dataset/DATASET_REGISTER.md) |
| Training | 416 px, batch 16, 25 epochs, seed 42, early-stop patience 8, augmentation = HSV / flip / scale / ±5° rotation / mosaic, CPU (i5-1340P) |
| Artifacts | `models/best.pt`, `models/training_config.json`, `models/eval_metrics.json`, `models/eval_report.md`, `models/eval/` (PR curves, confusion matrix), `models/error_analysis/` (FP/FN examples) |

Results on the held-out test split are in [`models/eval_report.md`](models/eval_report.md).

Reproduce:
```bash
python training/download_datasets.py            # ~2 GB from Hugging Face
python training/prepare_dataset.py              # builds dataset/yolo + configs/data.yaml + register
python training/train.py --epochs 25 --imgsz 416 --batch 16
python training/evaluate.py --split test --conf 0.35
```

## Module 2 — real-time pipeline

```
frame ─► YOLO ─► class/conf filter ─► zone filter ─► temporal window ─► state machine ─► overlay + evidence + events + alerts
                                                           ▲
                                              sensors (ESP32 / simulator)
```

**Decision engine** (`decision_engine/engine.py`, 15 unit tests in `tests/`):

| State | Enter when | Leave when |
|---|---|---|
| NORMAL | — | possible or strong hits accumulate |
| WARNING | ≥ 3 detections ≥ 0.35 conf inside a 3 s window | nothing ≥ 0.25 for 4 s → NORMAL |
| CONFIRMED | ≥ 10 detections ≥ 0.55 conf spanning ≥ 2 s (≥ 6 when sensors elevated) | nothing ≥ 0.25 for 4 s → RECOVERY |
| RECOVERY | after CONFIRMED clears or operator acknowledges | 10 s stable → NORMAL; re-appearance → CONFIRMED |
| SENSOR_WARNING | sensors elevated ≥ 5 s with no visual target | sensors normal → NORMAL; visual → WARNING/CONFIRMED |

Never triggers on a single frame; uses separate enter/clear thresholds (hysteresis); ignores stale sensor data
(fail-safe); manual emergency stop blocks every physical output. All numbers live in
[`configs/thresholds.yaml`](configs/thresholds.yaml).

**Responses per state (PDF §13):** WARNING → dashboard warning + log + snapshot. CONFIRMED → buzzer + notification
(console / log / Telegram / email) + evidence + event record (+ isolated low-voltage actuator if enabled). RECOVERY →
clear after the recovery period.

**Backend API** (`backend/app.py`, FastAPI + SQLite, docs at `/docs`):

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | service health |
| GET | `/status` | current state, sensors, latest detections, open events, e-stop |
| GET | `/devices`, `/devices/{id}` | devices + connectivity |
| POST | `/sensors` | sensor reading `{device_id, smoke, temperature, timestamp}` |
| POST | `/detections` | AI predictions + engine state from the inference process |
| GET | `/events`, `/events/{id}` | event history / details + evidence + notifications |
| POST | `/events/{id}/ack` | acknowledge (relayed to the inference process) |
| POST | `/control/estop` | manual emergency stop |
| GET | `/stream/{device_id}` | MJPEG live view with boxes |

Tables: `devices`, `sensor_readings`, `detections`, `events`, `notifications` (`backend/db.py`).

**Dashboard** (`dashboard/`, plain HTML/CSS/JS): live camera with boxes, NORMAL/WARNING/CONFIRMED status,
sensor gauges + chart, latest detections, event timeline with evidence and acknowledge buttons, history, device
health, notification log, emergency stop.

## Configuration (PDF §23)

| File | Contents |
|---|---|
| `configs/data.yaml` | dataset paths / classes (generated) |
| `configs/model_config.yaml` | checkpoint, image size, NMS |
| `configs/thresholds.yaml` | warning / confirmed / clear thresholds, window, sensor fusion, zone, responses |
| `configs/device_config.yaml` | camera source, device id / location, backend URL, evidence |
| `configs/notification_config.yaml` | channels (secrets in `.env`, never committed) |

## Tests

```bash
python -m pytest tests/ -q                                  # decision engine + backend API
python tests/hard_negative_test.py --source path/to/steam_video.mp4   # false alarms / hour on negatives
```

## Project layout

```
dataset/  models/  training/  inference/  vision/  decision_engine/  iot/  backend/  dashboard/
notifications/  tests/  configs/  logs/  evidence/  demo_media/  requirements.txt  README.md  DEMO.md
```

## Safety and scope

Physical automation only drives isolated low-voltage prototype loads (buzzer, LED, mini pump via relay). Never
connect the prototype to mains power, building fire pumps, gas systems or certified suppression equipment.
This is an academic prototype and must not be presented as a replacement for certified fire protection.
