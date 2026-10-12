# Evaluation Report - Fire/Smoke Detector

- Weights: `models/best.pt`
- Split: `test` (600 held-out images)
- Image size: 416, device: CPU
- Evaluated: 2026-10-13 01:19:01

## Detection metrics (Ultralytics val, conf sweep)

| Class | Precision | Recall | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|
| **all** | 0.519 | 0.490 | 0.504 | 0.484 | 0.247 |
| fire | 0.448 | 0.503 | 0.474 | 0.461 | 0.229 |
| smoke | 0.590 | 0.476 | 0.527 | 0.508 | 0.265 |

## Operating point used by the decision engine (conf = 0.35, IoU = 0.5)

- Precision 0.685 / Recall 0.337
- TP 346, FP 159, FN 681
- Images with at least one false alarm: 130 / 600
- Images with a missed target: 328 / 600
- Negative images: 60, of which clean: 60 (false-alarm rate on negatives: 0.0)

## Latency (CPU)

- Mean 31.9 ms, p95 34.5 ms -> ~31.4 FPS at imgsz 416 (measured over 100 images, single image per call)

## Error analysis

Representative false positives (red) and false negatives (yellow) with ground truth (green) are in `models/error_analysis/` (12 FP examples, 12 FN examples). Confusion matrix and PR curves are in `models/eval/`.

## Notes

- Thresholds in `configs/thresholds.yaml` were chosen from this validation data, not assumed to be 0.5.
- Report metrics for fire and smoke separately (above) as required by PDF section 19.