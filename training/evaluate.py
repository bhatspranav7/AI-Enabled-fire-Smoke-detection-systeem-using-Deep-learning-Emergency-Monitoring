"""Module 1 / step 3: held-out evaluation + error analysis + latency benchmark.

Produces (PDF sections 9.2, 10.3, 19):
    models/eval_metrics.json        precision / recall / F1 / mAP@0.5 / mAP@0.5:0.95, overall + per class
    models/eval_report.md           human-readable report incl. latency/FPS and FP/FN examples
    models/eval/                    confusion matrix, PR curves (from Ultralytics)
    models/error_analysis/          annotated false-positive and false-negative examples

Usage:
    python training/evaluate.py --weights models/best.pt --split test --conf 0.35
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

import cv2
import numpy as np
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def load_gt(label_path: pathlib.Path, w: int, h: int):
    boxes = []
    if label_path.exists():
        for line in label_path.read_text().splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            c, cx, cy, bw, bh = int(float(p[0])), *map(float, p[1:5])
            boxes.append((c, (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return boxes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "models" / "best.pt"))
    ap.add_argument("--data", default=str(ROOT / "configs" / "data.yaml"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--conf", type=float, default=0.35, help="operating confidence for FP/FN analysis")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--max-examples", type=int, default=12)
    ap.add_argument("--latency-images", type=int, default=100)
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    data = yaml.safe_load(pathlib.Path(args.data).read_text())
    names = {int(k): v for k, v in data["names"].items()} if isinstance(data["names"], dict) else dict(enumerate(data["names"]))
    ds_root = pathlib.Path(data["path"])
    img_dir = ds_root / data[args.split]
    lbl_dir = ds_root / "labels" / args.split

    # ---------------------------------------------------------------- 1. standard metrics
    eval_dir = ROOT / "models" / "eval"
    metrics = model.val(data=args.data, split=args.split, imgsz=args.imgsz, device="cpu",
                        plots=True, project=str(eval_dir.parent), name=eval_dir.name, exist_ok=True, verbose=False)
    box = metrics.box
    per_class = {}
    for i, name in names.items():
        if i in list(box.ap_class_index):
            idx = list(box.ap_class_index).index(i)
            p, r = float(box.p[idx]), float(box.r[idx])
            per_class[name] = {
                "precision": round(p, 4), "recall": round(r, 4),
                "f1": round(2 * p * r / (p + r), 4) if (p + r) else 0.0,
                "mAP50": round(float(box.ap50[idx]), 4), "mAP50-95": round(float(box.ap[idx]), 4),
            }
    mp, mr = float(box.mp), float(box.mr)
    overall = {
        "precision": round(mp, 4), "recall": round(mr, 4),
        "f1": round(2 * mp * mr / (mp + mr), 4) if (mp + mr) else 0.0,
        "mAP50": round(float(box.map50), 4), "mAP50-95": round(float(box.map), 4),
    }

    # ---------------------------------------------------------------- 2. FP / FN analysis + latency
    err_dir = ROOT / "models" / "error_analysis"
    err_dir.mkdir(parents=True, exist_ok=True)
    for f in err_dir.glob("*.jpg"):
        f.unlink()
    images = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}])
    counts = {"tp": 0, "fp": 0, "fn": 0, "false_alarm_images": 0, "missed_images": 0, "negatives": 0, "negatives_clean": 0}
    latencies = []
    fp_saved = fn_saved = 0
    for k, img_path in enumerate(images):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        t0 = time.perf_counter()
        res = model.predict(img, imgsz=args.imgsz, conf=args.conf, device="cpu", verbose=False)[0]
        if k < args.latency_images:
            latencies.append((time.perf_counter() - t0) * 1000)
        preds = [(int(c), *map(float, b)) for c, b in zip(res.boxes.cls.tolist(), res.boxes.xyxy.tolist())]
        confs = res.boxes.conf.tolist()
        gts = load_gt(lbl_dir / (img_path.stem + ".txt"), w, h)

        matched_gt = set()
        fp_boxes = []
        for pi, (pc, *pb) in enumerate(preds):
            best_j, best_iou = -1, 0.0
            for j, (gc, *gb) in enumerate(gts):
                if j in matched_gt or gc != pc:
                    continue
                v = iou(pb, gb)
                if v > best_iou:
                    best_j, best_iou = j, v
            if best_iou >= args.iou:
                matched_gt.add(best_j)
                counts["tp"] += 1
            else:
                counts["fp"] += 1
                fp_boxes.append((pc, pb, confs[pi]))
        fn_boxes = [g for j, g in enumerate(gts) if j not in matched_gt]
        counts["fn"] += len(fn_boxes)
        if not gts:
            counts["negatives"] += 1
            if not preds:
                counts["negatives_clean"] += 1
        if fp_boxes:
            counts["false_alarm_images"] += 1
        if fn_boxes:
            counts["missed_images"] += 1

        if (fp_boxes and fp_saved < args.max_examples) or (fn_boxes and fn_saved < args.max_examples):
            vis = img.copy()
            for gc, *gb in gts:  # ground truth = green
                cv2.rectangle(vis, (int(gb[0]), int(gb[1])), (int(gb[2]), int(gb[3])), (0, 200, 0), 2)
            for pc, pb, cf in fp_boxes:  # false positive = red
                cv2.rectangle(vis, (int(pb[0]), int(pb[1])), (int(pb[2]), int(pb[3])), (0, 0, 255), 2)
                cv2.putText(vis, f"FP {names[pc]} {cf:.2f}", (int(pb[0]), max(12, int(pb[1]) - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            for gc, *gb in fn_boxes:  # false negative = yellow
                cv2.rectangle(vis, (int(gb[0]), int(gb[1])), (int(gb[2]), int(gb[3])), (0, 220, 255), 2)
                cv2.putText(vis, f"FN {names[gc]}", (int(gb[0]), max(12, int(gb[1]) - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
            tag = "fp" if fp_boxes and fp_saved < args.max_examples else "fn"
            if tag == "fp":
                fp_saved += 1
            else:
                fn_saved += 1
            cv2.imwrite(str(err_dir / f"{tag}_{img_path.stem}.jpg"), vis)

    lat = {
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_ms": round(float(np.percentile(latencies, 95)), 1) if latencies else None,
        "fps": round(1000 / statistics.mean(latencies), 1) if latencies else None,
        "images": len(latencies), "imgsz": args.imgsz, "device": "cpu",
    }
    op = {
        "conf": args.conf, "iou": args.iou,
        "precision": round(counts["tp"] / max(1, counts["tp"] + counts["fp"]), 4),
        "recall": round(counts["tp"] / max(1, counts["tp"] + counts["fn"]), 4),
        **counts,
        "negative_image_false_alarm_rate": round(1 - counts["negatives_clean"] / counts["negatives"], 4) if counts["negatives"] else None,
    }

    out = {"weights": args.weights, "split": args.split, "images": len(images), "overall": overall,
           "per_class": per_class, "operating_point": op, "latency": lat,
           "evaluated": time.strftime("%Y-%m-%d %H:%M:%S")}
    (ROOT / "models" / "eval_metrics.json").write_text(json.dumps(out, indent=2))

    # ---------------------------------------------------------------- 3. markdown report
    def row(name, m):
        return f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['mAP50']:.3f} | {m['mAP50-95']:.3f} |"

    md = [
        "# Evaluation Report - Fire/Smoke Detector", "",
        f"- Weights: `{args.weights}`", f"- Split: `{args.split}` ({len(images)} held-out images)",
        f"- Image size: {args.imgsz}, device: CPU", f"- Evaluated: {out['evaluated']}", "",
        "## Detection metrics (Ultralytics val, conf sweep)", "",
        "| Class | Precision | Recall | F1 | mAP@0.5 | mAP@0.5:0.95 |", "|---|---|---|---|---|---|",
        row("**all**", overall), *[row(n, m) for n, m in per_class.items()], "",
        f"## Operating point used by the decision engine (conf = {args.conf}, IoU = {args.iou})", "",
        f"- Precision {op['precision']:.3f} / Recall {op['recall']:.3f}",
        f"- TP {op['tp']}, FP {op['fp']}, FN {op['fn']}",
        f"- Images with at least one false alarm: {op['false_alarm_images']} / {len(images)}",
        f"- Images with a missed target: {op['missed_images']} / {len(images)}",
        f"- Negative images: {op['negatives']}, of which clean: {op['negatives_clean']} "
        f"(false-alarm rate on negatives: {op['negative_image_false_alarm_rate']})", "",
        "## Latency (CPU)", "",
        f"- Mean {lat['mean_ms']} ms, p95 {lat['p95_ms']} ms -> ~{lat['fps']} FPS at imgsz {args.imgsz} "
        f"(measured over {lat['images']} images, single image per call)", "",
        "## Error analysis", "",
        f"Representative false positives (red) and false negatives (yellow) with ground truth (green) are in "
        f"`models/error_analysis/` ({fp_saved} FP examples, {fn_saved} FN examples). "
        "Confusion matrix and PR curves are in `models/eval/`.", "",
        "## Notes", "",
        "- Thresholds in `configs/thresholds.yaml` were chosen from this validation data, not assumed to be 0.5.",
        "- Report metrics for fire and smoke separately (above) as required by PDF section 19.",
    ]
    (ROOT / "models" / "eval_report.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
