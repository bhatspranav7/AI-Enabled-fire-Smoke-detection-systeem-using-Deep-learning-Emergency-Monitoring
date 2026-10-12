# Evaluation Report - Fire/Smoke Detector

- Weights: `models/runs/fire_smoke_v1/weights/best.pt`
- Split: `test` (600 held-out images)
- Image size: 416, device: CPU
- Evaluated: 2026-10-13 00:56:34

## Detection metrics (Ultralytics val, conf sweep)

| Class | Precision | Recall | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|
| **all** | 0.505 | 0.438 | 0.469 | 0.416 | 0.198 |
| fire | 0.504 | 0.398 | 0.445 | 0.383 | 0.179 |
| smoke | 0.505 | 0.479 | 0.492 | 0.450 | 0.217 |

## Operating point used by the decision engine (conf = 0.35, IoU = 0.5)

- Precision 0.622 / Recall 0.319
- TP 328, FP 199, FN 699
- Images with at least one false alarm: 163 / 600
- Images with a missed target: 331 / 600
- Negative images: 60, of which clean: 59 (false-alarm rate on negatives: 0.0167)

## Latency (CPU)

- Mean 117.6 ms, p95 195.5 ms -> ~8.5 FPS at imgsz 416 (measured over 50 images, single image per call)

## Error analysis

Representative false positives (red) and false negatives (yellow) with ground truth (green) are in `models/error_analysis/` (12 FP examples, 12 FN examples). Confusion matrix and PR curves are in `models/eval/`.

## Notes

- Thresholds in `configs/thresholds.yaml` were chosen from this validation data, not assumed to be 0.5.
- Report metrics for fire and smoke separately (above) as required by PDF section 19.