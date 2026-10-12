"""False-alarm test on hard negatives (PDF 11, 18.1, 19).

Runs the detector + decision engine over a negative source (steam / dust / fog / lights / normal scenes:
a video, a webcam session or a folder of images) and reports:
  * frames with any detection above min_conf, by class
  * WARNING / CONFIRMED transitions (= would-be false alarms) and false alarms per hour
  * max confidence seen

    python tests/hard_negative_test.py --source steam_video.mp4
    python tests/hard_negative_test.py --source 0 --seconds 60       # live webcam, 60 s
    python tests/hard_negative_test.py --source demo_media/negatives  # image folder
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decision_engine import DecisionEngine, Detection, State  # noqa: E402
from vision import Camera  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--weights", default=str(ROOT / "models" / "best.pt"))
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = whole video / folder once)")
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--label", default="hard-negative")
    args = ap.parse_args()

    from ultralytics import YOLO

    thr = yaml.safe_load((ROOT / "configs" / "thresholds.yaml").read_text())
    model = YOLO(args.weights)
    engine = DecisionEngine(thr)
    cam = Camera(args.source, loop_video=False, image_seconds=0.0)
    min_conf = float(thr["detection"].get("min_conf", 0.25))

    frames = det_frames = 0
    by_class = {"fire": 0, "smoke": 0}
    max_conf = 0.0
    transitions = []
    t0 = time.monotonic()
    seen_images = 0
    while True:
        ok, frame = cam.read()
        if cam.kind == "images":
            seen_images += 1
            if seen_images > len(cam._images):
                break
        if not ok:
            if cam.kind in ("video", "images"):
                break
            continue
        frames += 1
        r = model.predict(frame, imgsz=args.imgsz, conf=min_conf, device="cpu", verbose=False)[0]
        dets = []
        for c, cf, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
            cls = str(model.names[int(c)]).lower()
            if cls in by_class:
                dets.append(Detection(cls, float(cf), b))
                by_class[cls] += 1
                max_conf = max(max_conf, float(cf))
        if dets:
            det_frames += 1
        res = engine.update(dets, frame.shape[1], frame.shape[0])
        if res.transition and res.transition.new in (State.WARNING, State.CONFIRMED):
            transitions.append({"t": round(time.monotonic() - t0, 1), "to": res.transition.new.value, "reason": res.transition.reason})
        if args.seconds and time.monotonic() - t0 > args.seconds:
            break
    elapsed = max(1e-6, time.monotonic() - t0)
    confirmed = sum(1 for t in transitions if t["to"] == "CONFIRMED")
    warnings = sum(1 for t in transitions if t["to"] == "WARNING")
    report = {
        "label": args.label, "source": str(args.source), "frames": frames, "seconds": round(elapsed, 1),
        "frames_with_detection": det_frames, "frame_detection_rate": round(det_frames / max(1, frames), 4),
        "detections_by_class": by_class, "max_confidence": round(max_conf, 3),
        "warning_transitions": warnings, "confirmed_transitions": confirmed,
        "false_alarms_per_hour": round(confirmed * 3600 / elapsed, 2),
        "warnings_per_hour": round(warnings * 3600 / elapsed, 2),
        "transitions": transitions,
    }
    out = ROOT / "logs" / f"hard_negative_{args.label}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("saved ->", out)


if __name__ == "__main__":
    main()
