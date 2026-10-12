# Phase-2 Demo Script

Goal: show **Module 1 (AI model)** and **Module 2 (real-time inference + decision engine + event log)** working
live, with evidence that it is a genuine engineering build (dataset register, metrics, false-alarm handling).

## 0. Before the demo (5 min)

1. `setup.bat` done on the demo laptop (one time). Webcam works.
2. Have a fire source for the camera: **a fire/smoke video playing on a phone** held in front of the webcam works best
   (search "campfire 4k" / "smoke rising" on YouTube). A lighter or candle also works if allowed in the room.
3. Have something *steam-like* for the negative test: a phone video of a kettle / steam, or a white cloth waved slowly.
4. Optional: put Telegram bot token + chat id in `.env` and set `telegram.enabled: true` in
   `configs/notification_config.yaml` to get a real phone notification with the evidence photo.
5. Start: `run_demo.bat` (or `run_demo.bat demo_media\images` if there is no webcam). Three windows + dashboard open.

## 1. Module 1 — the model (3 min)

Show, in this order:

- `dataset/DATASET_REGISTER.md` — two licensed public sources, indoor + outdoor, class mapping, stratified split,
  no video leakage between train/test. ("Diversity over near-duplicates", PDF §6.)
- `models/training_config.json` — exact config, seed, versions, hardware, training time.
- `models/eval_report.md` — precision / recall / F1 / mAP@0.5 / mAP@0.5:0.95 **separately for fire and smoke**,
  operating-point FP/FN counts, false-alarm rate on negative images, CPU latency/FPS.
- `models/eval/confusion_matrix.png`, `models/eval/PR_curve.png`, and 2–3 images from `models/error_analysis/`
  (green = ground truth, red = false positive, yellow = missed) — "this is how we chose the thresholds".

Say: "We did not invent an architecture; we built a domain-specific detector through dataset design, hard
negatives, threshold tuning and temporal logic — which is what the requirements call a genuine engineering build."

## 2. Module 2 — live pipeline (7 min)

| Step | Do | Point at |
|---|---|---|
| Normal | Camera on the room | Dashboard shows **NORMAL**, FPS/latency, sensors normal, device online |
| Single-frame robustness | Flash the fire video for < 1 s | Boxes appear but state stays NORMAL → "no single-frame triggers" |
| Warning | Hold the fire video steady | After ~1 s → **WARNING** (orange), snapshot saved, event appears in timeline |
| Confirmed | Keep holding (~2–3 s) | **CONFIRMED** (red, pulsing), PC buzzer + browser alarm, console/log notification, evidence image, event escalates in timeline, notification log row |
| Acknowledge | Click **Acknowledge** on the dashboard | Inference window shows ack → state **RECOVERY**, buzzer stops |
| Recovery | Remove the fire | After 10 s stable → **NORMAL**, event closed with duration + peak confidence |
| Hysteresis | Show fire again, then half-hide it so confidence drops | Stays CONFIRMED while anything ≥ 0.25 is visible; no flapping |
| Hard negative | Show steam / white cloth / phone torch | Little or no detections; stays NORMAL — false-alarm reduction |
| Sensor fusion | In the simulator window press `s` (smoke rising) with no fire | After 5 s → **SENSOR_WARNING** (cyan). Press `n` → NORMAL |
| Fusion speeds confirmation | Press `b` (smoke + heat) then show fire | CONFIRMED needs only 6 strong hits instead of 10 ("sensors elevated" in reason) |
| Sensor disconnect | Press `x` | Dashboard shows sensor data STALE; engine ignores it (fail-safe) |
| Camera loss | Unplug / cover webcam (or stop the video file) | "CAMERA LOST – reconnecting" frame, dashboard overlay, auto-reconnect when back |
| Network loss | Ctrl-C the backend window, keep inference running | Inference window shows "backend OFFLINE (buffering locally)" and keeps detecting; restart backend → recovers |
| Emergency stop | Click **EMERGENCY STOP** (or press `e` in the inference window) | Buzzer/actuator blocked even in CONFIRMED; "EMERGENCY STOP" on the overlay |
| History | Dashboard → Event History / Device Health | Events table with ack times, evidence gallery, device connectivity, notifications log |

Backend proof: open http://127.0.0.1:8000/docs and call `GET /events` and `GET /status` live.

## 3. Likely questions

- **Why YOLO11n?** Lightweight baseline first (PDF §5.2); runs at usable FPS on a laptop CPU; larger variants only if
  validation justifies the extra latency.
- **Why not just colour thresholds?** They fail on sunlight, lamps, steam (PDF §11). We use learned features + temporal
  persistence + sensor fusion + hysteresis.
- **False alarms/hour?** Measured with `tests/hard_negative_test.py` on negative videos; reported in the eval report.
- **What is novel?** We don't claim a novel architecture; the contribution is robust false-alarm reduction and a
  multi-stage automated response (PDF §20).
- **Safety?** Buzzer and relay are isolated low-voltage prototype outputs; never mains, never certified equipment.
  Manual e-stop exists; actuators fail safe on lost communication (ESP32 firmware).

## 4. If something breaks

- No webcam → `run_demo.bat demo_media\images` or a video file.
- Model not detecting the phone video → move closer, reduce glare, lower `warning_conf`/`confirm_conf` slightly in
  `configs/thresholds.yaml` and restart inference.
- Too many false alarms → raise `confirm_conf` / `confirm_min_hits`.
- Port 8000 busy → change `backend.url` in `configs/device_config.yaml` and the `--port` in the backend command.
