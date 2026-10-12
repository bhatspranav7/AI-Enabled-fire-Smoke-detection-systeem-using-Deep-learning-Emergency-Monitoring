"""SQLite storage for the backend (PDF 14.2 tables). Standard library only."""
from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
import time
from typing import Any, Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "fire_smoke.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY, name TEXT, location TEXT, kind TEXT, status TEXT, last_seen REAL
);
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, smoke REAL, temperature REAL, timestamp REAL
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, class TEXT, confidence REAL, bbox TEXT, timestamp REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, severity INTEGER, state TEXT, reason TEXT,
    start_time REAL, end_time REAL, evidence_path TEXT, acknowledged INTEGER DEFAULT 0, ack_time REAL,
    peak_confidence REAL, peak_class TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, channel TEXT, sent_at REAL, status TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_det_ts ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_evt_start ON events(start_time);
"""


class Database:
    def __init__(self, path: pathlib.Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def _rows(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def _exec(self, sql: str, params=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    # ---------------------------------------------------------------- devices
    def upsert_device(self, id: str, name: str = "", location: str = "", kind: str = "camera", status: str = "online"):
        self._exec(
            "INSERT INTO devices(id,name,location,kind,status,last_seen) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=COALESCE(NULLIF(excluded.name,''),name), "
            "location=COALESCE(NULLIF(excluded.location,''),location), kind=excluded.kind, status=excluded.status, last_seen=excluded.last_seen",
            (id, name, location, kind, status, time.time()),
        )

    def touch_device(self, id: str, kind: str = "camera"):
        self.upsert_device(id, kind=kind)

    def devices(self, online_after: float = 15.0) -> list[dict]:
        now = time.time()
        rows = self._rows("SELECT * FROM devices ORDER BY id")
        for r in rows:
            r["online"] = r["last_seen"] is not None and (now - r["last_seen"]) < online_after
            r["status"] = "online" if r["online"] else "offline"
        return rows

    def device(self, id: str) -> Optional[dict]:
        rows = [d for d in self.devices() if d["id"] == id]
        return rows[0] if rows else None

    # ---------------------------------------------------------------- sensors
    def add_sensor(self, device_id: str, smoke: float, temperature: float, timestamp: float) -> int:
        return self._exec("INSERT INTO sensor_readings(device_id,smoke,temperature,timestamp) VALUES(?,?,?,?)",
                          (device_id, smoke, temperature, timestamp))

    def latest_sensor(self, device_id: Optional[str] = None) -> Optional[dict]:
        if device_id:
            rows = self._rows("SELECT * FROM sensor_readings WHERE device_id=? ORDER BY timestamp DESC LIMIT 1", (device_id,))
        else:
            rows = self._rows("SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 1")
        return rows[0] if rows else None

    def recent_sensors(self, seconds: float = 600, limit: int = 600) -> list[dict]:
        return self._rows("SELECT * FROM sensor_readings WHERE timestamp>=? ORDER BY timestamp DESC LIMIT ?",
                          (time.time() - seconds, limit))[::-1]

    # ---------------------------------------------------------------- detections
    def add_detections(self, device_id: str, dets: list[dict], timestamp: float) -> None:
        with self.lock:
            self.conn.executemany(
                "INSERT INTO detections(device_id,class,confidence,bbox,timestamp) VALUES(?,?,?,?,?)",
                [(device_id, d["cls"], float(d["conf"]), json.dumps([round(float(v), 1) for v in d["bbox"]]), timestamp) for d in dets],
            )
            self.conn.commit()

    def recent_detections(self, limit: int = 20) -> list[dict]:
        rows = self._rows("SELECT * FROM detections ORDER BY timestamp DESC LIMIT ?", (limit,))
        for r in rows:
            r["bbox"] = json.loads(r["bbox"])
        return rows

    # ---------------------------------------------------------------- events
    def create_event(self, device_id: str, severity: int, state: str, reason: str, start_time: float,
                     evidence_path: Optional[str], peak_confidence: Optional[float], peak_class: Optional[str]) -> int:
        return self._exec(
            "INSERT INTO events(device_id,severity,state,reason,start_time,evidence_path,peak_confidence,peak_class) VALUES(?,?,?,?,?,?,?,?)",
            (device_id, severity, state, reason, start_time, evidence_path, peak_confidence, peak_class),
        )

    def update_event(self, event_id: int, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE events SET {cols} WHERE id=?", (*fields.values(), event_id))

    def events(self, limit: int = 50, state: Optional[str] = None, open_only: bool = False) -> list[dict]:
        sql, params = "SELECT * FROM events", []
        where = []
        if state:
            where.append("state=?"); params.append(state)
        if open_only:
            where.append("end_time IS NULL")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def event(self, event_id: int) -> Optional[dict]:
        rows = self._rows("SELECT * FROM events WHERE id=?", (event_id,))
        if not rows:
            return None
        ev = rows[0]
        ev["notifications"] = self._rows("SELECT * FROM notifications WHERE event_id=? ORDER BY sent_at", (event_id,))
        return ev

    def ack_event(self, event_id: int) -> bool:
        if not self._rows("SELECT id FROM events WHERE id=?", (event_id,)):
            return False
        self._exec("UPDATE events SET acknowledged=1, ack_time=? WHERE id=?", (time.time(), event_id))
        return True

    # ---------------------------------------------------------------- notifications
    def add_notification(self, event_id: Optional[int], channel: str, status: str, detail: str = "") -> int:
        return self._exec("INSERT INTO notifications(event_id,channel,sent_at,status,detail) VALUES(?,?,?,?,?)",
                          (event_id, channel, time.time(), status, detail))

    def notifications(self, limit: int = 50) -> list[dict]:
        return self._rows("SELECT * FROM notifications ORDER BY sent_at DESC LIMIT ?", (limit,))

    # ---------------------------------------------------------------- stats
    def stats(self) -> dict:
        day_ago = time.time() - 86400
        r = self._rows("SELECT COUNT(*) c FROM events WHERE start_time>=?", (day_ago,))[0]["c"]
        c = self._rows("SELECT COUNT(*) c FROM events WHERE state='CONFIRMED' AND start_time>=?", (day_ago,))[0]["c"]
        d = self._rows("SELECT COUNT(*) c FROM detections WHERE timestamp>=?", (day_ago,))[0]["c"]
        return {"events_24h": r, "confirmed_24h": c, "detections_24h": d}
