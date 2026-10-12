"""Module 1 / step 2: train the fire/smoke YOLO detector.

Baseline per PDF section 8.2: lightweight pretrained YOLO, 640 (416 on CPU), fixed seed,
best-validation checkpoint, default Ultralytics augmentation (HSV, flip, scale, mosaic)
plus small rotation.

Usage (CPU, overnight-friendly):
    python training/train.py --model yolo11n.pt --epochs 30 --imgsz 416 --batch 16

Outputs:
    models/runs/<name>/          full Ultralytics run (weights, results.csv, plots)
    models/best.pt               best-validation checkpoint (used by inference)
    models/training_config.json  exact config, package versions, hardware, timings
"""
from __future__ import annotations

import argparse
import json
import pathlib
import platform
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo11n.pt", help="pretrained checkpoint (downloaded by Ultralytics)")
    ap.add_argument("--data", default=str(ROOT / "configs" / "data.yaml"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--name", default="fire_smoke_v1")
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fraction", type=float, default=1.0, help="fraction of the train split to use")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--cache", default="ram", help="ram | disk | False  (ram speeds up CPU training a lot)")
    args = ap.parse_args()
    cache = False if str(args.cache).lower() == "false" else args.cache

    import torch
    import ultralytics
    from ultralytics import YOLO

    run_dir = ROOT / "models" / "runs"
    t0 = time.time()
    model = YOLO(args.model)
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        project=str(run_dir),
        name=args.name,
        exist_ok=True,
        seed=args.seed,
        deterministic=True,
        patience=args.patience,
        fraction=args.fraction,
        cache=cache,
        # augmentation (PDF 8.2: brightness/contrast, flip, scale, limited rotation)
        hsv_h=0.015, hsv_s=0.6, hsv_v=0.5,
        fliplr=0.5, scale=0.5, degrees=5.0, translate=0.1,
        mosaic=1.0, close_mosaic=5,
        plots=True,
        verbose=True,
        resume=args.resume,
    )
    elapsed = time.time() - t0

    best = run_dir / args.name / "weights" / "best.pt"
    dst = ROOT / "models" / "best.pt"
    if best.exists():
        shutil.copy2(best, dst)
        print(f"best checkpoint -> {dst}")

    cfg = {
        "run": args.name,
        "base_model": args.model,
        "data": args.data,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "seed": args.seed,
        "fraction": args.fraction,
        "patience": args.patience,
        "augmentation": {"hsv_h": 0.015, "hsv_s": 0.6, "hsv_v": 0.5, "fliplr": 0.5,
                          "scale": 0.5, "degrees": 5.0, "translate": 0.1, "mosaic": 1.0},
        "training_time_minutes": round(elapsed / 60, 1),
        "hardware": {"device": args.device, "cpu": platform.processor(), "machine": platform.machine(),
                     "cuda": torch.cuda.is_available()},
        "versions": {"python": platform.python_version(), "torch": torch.__version__,
                     "ultralytics": ultralytics.__version__},
        "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        cfg["final_val_metrics"] = {
            "precision": float(results.box.mp),
            "recall": float(results.box.mr),
            "mAP50": float(results.box.map50),
            "mAP50-95": float(results.box.map),
        }
    except Exception:
        pass
    (ROOT / "models" / "training_config.json").write_text(json.dumps(cfg, indent=2))
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
