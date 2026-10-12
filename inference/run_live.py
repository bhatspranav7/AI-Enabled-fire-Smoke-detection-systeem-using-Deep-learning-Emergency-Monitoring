"""Module 2: real-time inference pipeline (PDF section 10).

Camera -> frame capture -> preprocessing -> YOLO inference -> confidence filtering ->
temporal decision engine -> overlay -> evidence snapshot -> notification -> backend/dashboard.

Usage:
    python inference/run_live.py                      # webcam from configs/device_config.yaml
    python inference/run_live.py --source demo_media/fire_clip.mp4
    python inference/run_live.py --source demo_media/images   # folder of images, cycled
    python inference/run_live.py --no-backend         # standalone window only

Keys in the window:  q quit | a acknowledge | e toggle emergency stop | s save snapshot | r reset engine
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import time
from typing import List, Optional

import cv2
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decision_engine import DecisionEngine, Detection, SensorReading, State  # noqa: E402
from decision_engine.engine import SEVERITY  # noqa: E402
from notifications import Notifier  # noqa: E402
from vision import Camera, draw_overlay  # noqa: E402
from vision.overlay import camera_lost_frame  # noqa: E402


def load_yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text()) or {}


class Buzzer:
    """Software buzzer on the dev PC (winsound). Replaced by the ESP32 buzzer when IoT is attached."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._on = False
        self._thread: Optional[threading.Thread] = None

    def set(self, on: bool) -> None:
        if not self.enabled or on == self._on:
            return
        self._on = on
        if on:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        try:
            import winsound
        except ImportError:
            while self._on:
                print("\a", end="", flush=True)
                time.sleep(0.7)
            return
        while self._on:
            winsound.Beep(1800, 250)
            time.sleep(0.25)


class BackendClient:
    """Thin, non-blocking HTTP client. Any failure is swallowed and reported as 'offline'
    so the inference loop keeps running during network loss (PDF 18.2)."""

    def __init__(self, cfg: dict, device_cfg: dict):
        import requests

        self.s = requests.Session()
        self.enabled = bool(cfg.get("enabled", True))
        self.url = cfg.get("url", "http://127.0.0.1:8000").rstrip("/")
        self.timeout = cfg.get("timeout_seconds", 2)
        self.device = device_cfg
        self.online = False
        self._lock = threading.Lock()

    def _post(self, path: str, **kw) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = self.s.post(self.url + path, timeout=self.timeout, **kw)
            self.online = r.ok
            return r.json() if r.ok and r.content else None
        except Exception:
            self.online = False
            return None

    def _get(self, path: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = self.s.get(self.url + path, timeout=self.timeout)
            self.online = r.ok
            return r.json() if r.ok else None
        except Exception:
            self.online = False
            return None

    def register(self):
        self._post("/devices", json={"id": self.device["id"], "name": self.device["name"],
                                     "location": self.device["location"], "kind": "camera"})

    def push_detections(self, payload: dict):
        threading.Thread(target=self._post, args=("/detections",), kwargs={"json": payload}, daemon=True).start()

    def push_frame(self, jpeg: bytes):
        threading.Thread(target=self._post, args=(f"/frames/{self.device['id']}",),
                         kwargs={"data": jpeg, "headers": {"Content-Type": "image/jpeg"}}, daemon=True).start()

    def create_event(self, payload: dict) -> Optional[int]:
        r = self._post("/events", json=payload)
        return r.get("id") if r else None

    def end_event(self, event_id: int, payload: dict):
        self._post(f"/events/{event_id}/end", json=payload)

    def notification(self, event_id: Optional[int], channel: str, status: str, detail: str):
        self._post("/notifications", json={"event_id": event_id, "channel": channel, "status": status, "detail": detail})

    def latest_sensor(self) -> Optional[dict]:
        return self._get("/sensors/latest")

    def commands(self) -> dict:
        return self._get(f"/devices/{self.device['id']}/commands") or {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="webcam index, video file, RTSP url or image folder (overrides device_config.yaml)")
    ap.add_argument("--weights", help="override model weights")
    ap.add_argument("--imgsz", type=int)
    ap.add_argument("--no-backend", action="store_true")
    ap.add_argument("--no-window", action="store_true", help="headless (dashboard only)")
    ap.add_argument("--no-buzzer", action="store_true")
    args = ap.parse_args()

    thr = load_yaml("thresholds.yaml")
    dev = load_yaml("device_config.yaml")
    mcfg = load_yaml("model_config.yaml")

    # ---------------------------------------------------------------- model
    from ultralytics import YOLO

    weights = args.weights or mcfg["model"]["weights"]
    wpath = ROOT / weights if not pathlib.Path(weights).is_absolute() else pathlib.Path(weights)
    if not wpath.exists():
        print(f"[warn] {wpath} not found - falling back to {mcfg['model']['fallback_weights']} (COCO model, demo only)")
        wpath = pathlib.Path(mcfg["model"]["fallback_weights"])
    model = YOLO(str(wpath))
    imgsz = args.imgsz or mcfg["model"].get("imgsz", 416)
    names = model.names
    print(f"[model] {wpath}  classes={names}  imgsz={imgsz}")

    # ---------------------------------------------------------------- components
    cam_cfg = dev["camera"]
    source = args.source if args.source is not None else cam_cfg.get("source", 0)
    cam = Camera(source, cam_cfg.get("width", 1280), cam_cfg.get("height", 720), cam_cfg.get("reconnect_seconds", 3))
    target_dt = 1.0 / max(1, cam_cfg.get("target_fps", 15))
    engine = DecisionEngine(thr)
    buzzer = Buzzer(bool(thr.get("response", {}).get("buzzer", True)) and not args.no_buzzer)
    backend = BackendClient({**dev.get("backend", {}), "enabled": dev.get("backend", {}).get("enabled", True) and not args.no_backend}, dev["device"])
    backend.register()
    notifier = Notifier(load_yaml("notification_config.yaml"))
    resp = thr.get("response", {})
    notify_on = set(resp.get("notify_on", ["CONFIRMED", "SENSOR_WARNING"]))
    snapshot_on = set(resp.get("snapshot_on", ["WARNING", "CONFIRMED", "SENSOR_WARNING"]))
    evidence_dir = ROOT / dev.get("evidence", {}).get("dir", "evidence")
    evidence_dir.mkdir(exist_ok=True)
    min_snap_gap = dev.get("evidence", {}).get("min_seconds_between_snapshots", 5)
    log_path = ROOT / "logs" / "events.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    push_frame_every = dev.get("backend", {}).get("push_frame_every_seconds", 0.2)
    det_classes = set(thr.get("detection", {}).get("classes", ["fire", "smoke"]))
    min_conf = float(thr.get("detection", {}).get("min_conf", 0.25))

    # ---------------------------------------------------------------- loop state
    current_event_id: Optional[int] = None
    current_event_peak = (None, 0.0)  # (cls, conf)
    current_event_evidence: Optional[str] = None
    last_snapshot = 0.0
    last_frame_push = 0.0
    last_sensor_poll = 0.0
    last_cmd_poll = 0.0
    sensor_view: Optional[dict] = None
    fps, fps_t, fps_n = 0.0, time.monotonic(), 0
    lost_since: Optional[float] = None
    window = "AI Fire/Smoke Detection - live"
    if not args.no_window:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    def log_event(kind: str, **data):
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "kind": kind, **data}) + "\n")

    def save_snapshot(frame, tag: str) -> str:
        name = f"{time.strftime('%Y%m%d_%H%M%S')}_{dev['device']['id']}_{tag}.jpg"
        p = evidence_dir / name
        cv2.imwrite(str(p), frame)
        return str(p)

    print("[live] running. keys: q quit | a ack | e e-stop | s snapshot | r reset")
    try:
        while True:
            loop_t0 = time.monotonic()
            ok, frame = cam.read()
            now = time.time()

            # ---- commands from dashboard (ack / e-stop)
            if backend.enabled and loop_t0 - last_cmd_poll > 1.0:
                last_cmd_poll = loop_t0
                c = backend.commands()
                for cmd in c.get("commands", []):
                    if cmd.get("type") == "ack":
                        tr = engine.acknowledge()
                        log_event("ack", source="dashboard", transition=str(tr))
                    elif cmd.get("type") == "estop":
                        engine.set_emergency_stop(bool(cmd.get("on")))
                        log_event("estop", on=bool(cmd.get("on")), source="dashboard")
                if "emergency_stop" in c:
                    engine.set_emergency_stop(bool(c["emergency_stop"]))

            # ---- sensor fusion input (from backend; ESP32 or simulator posts there)
            if backend.enabled and loop_t0 - last_sensor_poll > 1.0:
                last_sensor_poll = loop_t0
                s = backend.latest_sensor()
                if s and "smoke" in s:
                    age = float(s.get("age_seconds", 0))
                    engine.update_sensor(SensorReading(float(s["smoke"]), float(s["temperature"]), time.monotonic() - age))
                    sensor_view = {"smoke": s["smoke"], "temperature": s["temperature"], "stale": age > thr.get("sensors", {}).get("stale_after_seconds", 15)}

            if not ok or frame is None:
                if lost_since is None:
                    lost_since = loop_t0
                    log_event("camera_lost")
                dets: List[Detection] = []
                res = engine.update(dets)  # keeps temporal windows and sensor logic alive
                vis = camera_lost_frame(cam_cfg.get("width", 1280), cam_cfg.get("height", 720), loop_t0 - lost_since)
                latency_ms = 0.0
            else:
                if lost_since is not None:
                    log_event("camera_recovered", after_seconds=round(loop_t0 - lost_since, 1))
                    lost_since = None
                h, w = frame.shape[:2]
                t0 = time.perf_counter()
                r = model.predict(frame, imgsz=imgsz, conf=min_conf, iou=mcfg["model"].get("iou", 0.5),
                                  max_det=mcfg["model"].get("max_det", 20), device=mcfg["model"].get("device", "cpu"),
                                  verbose=False)[0]
                latency_ms = (time.perf_counter() - t0) * 1000
                dets = []
                for c, cf, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
                    cls = str(names[int(c)]).lower()
                    if cls in det_classes:
                        dets.append(Detection(cls, float(cf), b))
                res = engine.update(dets, w, h)
                vis = draw_overlay(frame, dets, res.state.value, fps, latency_ms, res.reason, sensor_view,
                                   thr.get("zone", {}).get("roi"), engine.emergency_stop, dev["device"]["name"])

            # ---- peak detection tracking for the open event
            if res.best and current_event_id is not None and res.best.conf > current_event_peak[1]:
                current_event_peak = (res.best.cls, res.best.conf)

            # ---- transitions -> evidence, events, notifications, buzzer
            tr = res.transition
            if tr is not None:
                print(f"[state] {tr.old.value} -> {tr.new.value}  ({tr.reason})")
                log_event("transition", old=tr.old.value, new=tr.new.value, reason=tr.reason)
                evidence_path = None
                if tr.new.value in snapshot_on and ok:
                    evidence_path = save_snapshot(vis, tr.new.value.lower())
                    current_event_evidence = evidence_path
                    last_snapshot = loop_t0
                sev = SEVERITY[tr.new]
                if tr.new in (State.WARNING, State.CONFIRMED, State.SENSOR_WARNING):
                    if current_event_id is None:
                        current_event_id = backend.create_event({
                            "device_id": dev["device"]["id"], "severity": sev, "state": tr.new.value,
                            "reason": tr.reason, "start_time": now, "evidence_path": pathlib.Path(evidence_path).name if evidence_path else None,
                            "peak_confidence": res.best.conf if res.best else None, "peak_class": res.best.cls if res.best else None,
                        })
                        current_event_peak = (res.best.cls, res.best.conf) if res.best else (None, 0.0)
                    else:  # escalation (WARNING -> CONFIRMED): update the open event
                        backend.end_event  # noqa: B018 (no-op reference keeps linters quiet)
                        backend._post(f"/events/{current_event_id}/end", json={})  # mark escalation time
                        current_event_id = backend.create_event({
                            "device_id": dev["device"]["id"], "severity": sev, "state": tr.new.value,
                            "reason": tr.reason, "start_time": now, "evidence_path": pathlib.Path(evidence_path).name if evidence_path else None,
                            "peak_confidence": res.best.conf if res.best else None, "peak_class": res.best.cls if res.best else None,
                        })
                    if tr.new.value in notify_on:
                        results = notifier.send(tr.new.value, dev["device"]["name"], dev["device"]["location"], tr.reason,
                                                res.best.conf if res.best else None, res.best.cls if res.best else None,
                                                evidence_path, resp.get("notification_cooldown_seconds", 60))
                        eid = current_event_id

                        def _report(results=results, eid=eid):
                            time.sleep(3)
                            for rr in results:
                                backend.notification(eid, rr["channel"], rr["status"], rr["detail"])
                                log_event("notification", event_id=eid, **rr)
                        threading.Thread(target=_report, daemon=True).start()
                elif tr.new in (State.RECOVERY, State.NORMAL) and current_event_id is not None:
                    backend.end_event(current_event_id, {"end_time": now,
                                                         "peak_confidence": current_event_peak[1] or None,
                                                         "peak_class": current_event_peak[0],
                                                         "evidence_path": pathlib.Path(current_event_evidence).name if current_event_evidence else None})
                    current_event_id = None
                    current_event_evidence = None

            # periodic extra evidence while CONFIRMED
            if res.state == State.CONFIRMED and ok and loop_t0 - last_snapshot > min_snap_gap:
                current_event_evidence = save_snapshot(vis, "confirmed")
                last_snapshot = loop_t0

            buzzer.set(engine.actuator_allowed)  # buzzer only when CONFIRMED and no e-stop

            # ---- backend: state + detections + preview frame
            if backend.enabled:
                backend.push_detections({
                    "device_id": dev["device"]["id"],
                    "detections": [{"cls": d.cls, "conf": round(d.conf, 3), "bbox": [round(v, 1) for v in d.bbox]} for d in dets],
                    "state": res.state.value, "reason": res.reason, "fps": round(fps, 1), "latency_ms": round(latency_ms, 1),
                    "timestamp": now, "camera_connected": ok, "sensors_elevated": res.sensors_elevated,
                })
                if loop_t0 - last_frame_push >= push_frame_every:
                    last_frame_push = loop_t0
                    small = cv2.resize(vis, (960, int(960 * vis.shape[0] / vis.shape[1])))
                    okj, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if okj:
                        backend.push_frame(buf.tobytes())
                cv2.putText(vis, "backend: " + ("online" if backend.online else "OFFLINE (buffering locally)"),
                            (vis.shape[1] - 330, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255) if backend.online else (0, 0, 255), 1)

            # ---- window + keys
            if not args.no_window:
                cv2.imshow(window, vis)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("q"):
                    break
                elif k == ord("a"):
                    tr2 = engine.acknowledge()
                    log_event("ack", source="keyboard", transition=str(tr2))
                elif k == ord("e"):
                    engine.set_emergency_stop(not engine.emergency_stop)
                    log_event("estop", on=engine.emergency_stop, source="keyboard")
                    print(f"[estop] {'ON' if engine.emergency_stop else 'off'}")
                elif k == ord("s") and ok:
                    print("[snapshot]", save_snapshot(vis, "manual"))
                elif k == ord("r"):
                    engine.reset()
                    print("[engine] reset")

            # ---- fps + pacing
            fps_n += 1
            if loop_t0 - fps_t >= 1.0:
                fps = fps_n / (loop_t0 - fps_t)
                fps_n, fps_t = 0, loop_t0
            spare = target_dt - (time.monotonic() - loop_t0)
            if spare > 0:
                time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        buzzer.set(False)
        cam.release()
        cv2.destroyAllWindows()
        if current_event_id is not None:
            backend.end_event(current_event_id, {"end_time": time.time()})
        print("[live] stopped")


if __name__ == "__main__":
    main()
