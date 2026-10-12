"""FastAPI backend (PDF sections 14 & 17).

Run:  uvicorn backend.app:app --host 0.0.0.0 --port 8000
Docs: http://127.0.0.1:8000/docs      Dashboard: http://127.0.0.1:8000/

Endpoints required by the PDF:
  GET  /health             service health
  GET  /status             current state (per device, sensors, latest detection, e-stop)
  GET  /devices            devices + connectivity
  GET  /devices/{id}       device details
  POST /sensors            sensor reading from ESP32 / simulator
  POST /detections         AI predictions from the inference process
  GET  /events             event history
  GET  /events/{id}        event details + evidence + notifications
  POST /events/{id}/ack    acknowledge event
Extra (needed by the live pipeline / dashboard):
  POST /frames/{device_id} latest annotated JPEG   GET /live/{device_id}.jpg   GET /stream/{device_id} (MJPEG)
  POST /events, POST /events/{id}/end, POST /notifications, GET /sensors/latest, GET /sensors/recent,
  GET /detections/recent, POST /control/estop, GET /devices/{id}/commands
"""
from __future__ import annotations

import collections
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import Database

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evidence"
DASHBOARD_DIR = ROOT / "dashboard"
EVIDENCE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI Fire/Smoke Detection Backend", version="1.0")
db = Database()

# ---------------------------------------------------------------- in-memory live state
_frames: Dict[str, bytes] = {}
_frame_ts: Dict[str, float] = {}
_frame_cv = threading.Condition()
_device_state: Dict[str, dict] = {}
_commands: Dict[str, collections.deque] = collections.defaultdict(collections.deque)
_estop = {"on": False, "since": None}
_started = time.time()


# ---------------------------------------------------------------- models
class SensorIn(BaseModel):
    device_id: str = "esp32-01"
    smoke: float
    temperature: float
    timestamp: Optional[float] = None


class DetectionItem(BaseModel):
    cls: str
    conf: float
    bbox: List[float]


class DetectionsIn(BaseModel):
    device_id: str = "cam01"
    detections: List[DetectionItem] = Field(default_factory=list)
    state: str = "NORMAL"
    reason: str = ""
    fps: float = 0.0
    latency_ms: float = 0.0
    timestamp: Optional[float] = None
    camera_connected: bool = True
    sensors_elevated: bool = False


class EventIn(BaseModel):
    device_id: str = "cam01"
    severity: int = 2
    state: str
    reason: str = ""
    start_time: Optional[float] = None
    evidence_path: Optional[str] = None
    peak_confidence: Optional[float] = None
    peak_class: Optional[str] = None


class EventEnd(BaseModel):
    end_time: Optional[float] = None
    evidence_path: Optional[str] = None
    peak_confidence: Optional[float] = None
    peak_class: Optional[str] = None


class NotificationIn(BaseModel):
    event_id: Optional[int] = None
    channel: str
    status: str
    detail: str = ""


class DeviceIn(BaseModel):
    id: str
    name: str = ""
    location: str = ""
    kind: str = "camera"


class EstopIn(BaseModel):
    on: bool


# ---------------------------------------------------------------- health / status
@app.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": round(time.time() - _started, 1), "time": time.time()}


@app.get("/status")
def status():
    devices = db.devices()
    cams = {d["id"]: d for d in devices if d["kind"] == "camera"}
    states = {}
    for dev_id, st in _device_state.items():
        states[dev_id] = {**st, "online": cams.get(dev_id, {}).get("online", False)}
    overall = "NORMAL"
    rank = {"NORMAL": 0, "RECOVERY": 1, "SENSOR_WARNING": 2, "WARNING": 2, "CONFIRMED": 3}
    for st in states.values():
        if rank.get(st.get("state", "NORMAL"), 0) > rank.get(overall, 0):
            overall = st["state"]
    sensor = db.latest_sensor()
    if sensor:
        sensor["stale"] = (time.time() - sensor["timestamp"]) > 15
    return {
        "overall_state": overall,
        "devices": states,
        "sensor": sensor,
        "latest_detections": db.recent_detections(5),
        "open_events": db.events(limit=10, open_only=True),
        "emergency_stop": _estop,
        "stats": db.stats(),
        "time": time.time(),
    }


# ---------------------------------------------------------------- devices
@app.get("/devices")
def devices():
    return db.devices()


@app.post("/devices")
def register_device(d: DeviceIn):
    db.upsert_device(d.id, d.name, d.location, d.kind)
    return {"ok": True}


@app.get("/devices/{device_id}")
def device(device_id: str):
    d = db.device(device_id)
    if not d:
        raise HTTPException(404, "unknown device")
    d["live_state"] = _device_state.get(device_id)
    if d["kind"] != "camera":
        d["latest_sensor"] = db.latest_sensor(device_id)
    return d


@app.post("/devices/{device_id}/heartbeat")
def heartbeat(device_id: str, kind: str = "camera"):
    db.touch_device(device_id, kind)
    return {"ok": True}


@app.get("/devices/{device_id}/commands")
def pop_commands(device_id: str):
    q = _commands[device_id]
    cmds = []
    while q:
        cmds.append(q.popleft())
    return {"commands": cmds, "emergency_stop": _estop["on"]}


# ---------------------------------------------------------------- sensors
@app.post("/sensors")
def post_sensor(s: SensorIn):
    ts = s.timestamp or time.time()
    db.touch_device(s.device_id, "sensor")
    rid = db.add_sensor(s.device_id, s.smoke, s.temperature, ts)
    return {"ok": True, "id": rid}


@app.get("/sensors/latest")
def sensors_latest(device_id: Optional[str] = None):
    s = db.latest_sensor(device_id)
    if s:
        s["age_seconds"] = round(time.time() - s["timestamp"], 1)
    return s or {}


@app.get("/sensors/recent")
def sensors_recent(seconds: float = 600):
    return db.recent_sensors(seconds)


# ---------------------------------------------------------------- detections
@app.post("/detections")
def post_detections(d: DetectionsIn):
    ts = d.timestamp or time.time()
    db.touch_device(d.device_id, "camera")
    if d.detections:
        db.add_detections(d.device_id, [x.model_dump() for x in d.detections], ts)
    _device_state[d.device_id] = {
        "state": d.state, "reason": d.reason, "fps": d.fps, "latency_ms": d.latency_ms,
        "camera_connected": d.camera_connected, "sensors_elevated": d.sensors_elevated,
        "detections": [x.model_dump() for x in d.detections], "updated": ts,
    }
    return {"ok": True, "emergency_stop": _estop["on"]}


@app.get("/detections/recent")
def detections_recent(limit: int = 20):
    return db.recent_detections(limit)


# ---------------------------------------------------------------- events
@app.get("/events")
def events(limit: int = 50, state: Optional[str] = None):
    return db.events(limit=limit, state=state)


@app.post("/events")
def create_event(e: EventIn):
    eid = db.create_event(e.device_id, e.severity, e.state, e.reason, e.start_time or time.time(),
                          e.evidence_path, e.peak_confidence, e.peak_class)
    return {"ok": True, "id": eid}


@app.get("/events/{event_id}")
def event(event_id: int):
    ev = db.event(event_id)
    if not ev:
        raise HTTPException(404, "unknown event")
    return ev


@app.post("/events/{event_id}/end")
def end_event(event_id: int, body: EventEnd):
    fields: Dict[str, Any] = {"end_time": body.end_time or time.time()}
    for k in ("evidence_path", "peak_confidence", "peak_class"):
        if getattr(body, k) is not None:
            fields[k] = getattr(body, k)
    db.update_event(event_id, **fields)
    return {"ok": True}


@app.post("/events/{event_id}/ack")
def ack_event(event_id: int):
    if not db.ack_event(event_id):
        raise HTTPException(404, "unknown event")
    ev = db.event(event_id)
    _commands[ev["device_id"]].append({"type": "ack", "event_id": event_id, "time": time.time()})
    return {"ok": True, "event": ev}


# ---------------------------------------------------------------- notifications
@app.post("/notifications")
def post_notification(n: NotificationIn):
    nid = db.add_notification(n.event_id, n.channel, n.status, n.detail)
    return {"ok": True, "id": nid}


@app.get("/notifications")
def notifications(limit: int = 50):
    return db.notifications(limit)


# ---------------------------------------------------------------- control
@app.post("/control/estop")
def estop(body: EstopIn):
    _estop["on"] = body.on
    _estop["since"] = time.time() if body.on else None
    for dev in list(_device_state) or ["cam01"]:
        _commands[dev].append({"type": "estop", "on": body.on, "time": time.time()})
    return _estop


@app.get("/control/estop")
def estop_get():
    return _estop


# ---------------------------------------------------------------- live frames
@app.post("/frames/{device_id}")
async def post_frame(device_id: str, request: Request):
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty body")
    with _frame_cv:
        _frames[device_id] = data
        _frame_ts[device_id] = time.time()
        _frame_cv.notify_all()
    return {"ok": True}


@app.get("/live/{device_id}.jpg")
def live_jpg(device_id: str):
    data = _frames.get(device_id)
    if not data:
        raise HTTPException(404, "no frame yet")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/stream/{device_id}")
def stream(device_id: str):
    def gen():
        last = 0.0
        while True:
            with _frame_cv:
                _frame_cv.wait_for(lambda: _frame_ts.get(device_id, 0.0) > last, timeout=1.0)
                data = _frames.get(device_id)
                ts = _frame_ts.get(device_id, 0.0)
            if data and ts > last:
                last = ts
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------------------------------------------------------------- evidence + dashboard
@app.get("/evidence/{name}")
def evidence(name: str):
    p = (EVIDENCE_DIR / pathlib.Path(name).name)
    if not p.exists():
        raise HTTPException(404, "not found")
    return FileResponse(p)


@app.get("/evidence")
def evidence_list(limit: int = 50):
    files = sorted(EVIDENCE_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [{"name": p.name, "time": p.stat().st_mtime, "url": f"/evidence/{p.name}"} for p in files]


@app.get("/", response_class=HTMLResponse)
def index():
    p = DASHBOARD_DIR / "index.html"
    if not p.exists():
        return HTMLResponse("<h1>Backend running</h1><p>Dashboard files missing. See /docs.</p>")
    return HTMLResponse(p.read_text(encoding="utf-8"))


app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR)), name="dashboard")
