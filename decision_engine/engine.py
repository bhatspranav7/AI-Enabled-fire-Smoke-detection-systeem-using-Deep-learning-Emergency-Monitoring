"""Temporal decision engine: turns per-frame detections (+ optional sensor readings)
into a stable NORMAL / WARNING / CONFIRMED / RECOVERY / SENSOR_WARNING state.

Design goals (PDF sections 11 & 13):
  * never trigger on a single unstable frame  -> persistence over a time window
  * separate enter/clear thresholds           -> hysteresis, no rapid switching
  * optional sensor fusion                    -> elevated sensors lower the bar for CONFIRMED,
                                                 persistent sensor-only evidence -> SENSOR_WARNING
  * zone logic                                -> ignore detections outside the ROI
  * fail safe                                 -> stale sensor readings are ignored

The engine is pure logic with an injectable clock so it can be unit-tested without a camera.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Iterable, List, Optional, Sequence


class State(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CONFIRMED = "CONFIRMED"
    RECOVERY = "RECOVERY"
    SENSOR_WARNING = "SENSOR_WARNING"


SEVERITY = {
    State.NORMAL: 0,
    State.RECOVERY: 1,
    State.SENSOR_WARNING: 2,
    State.WARNING: 2,
    State.CONFIRMED: 3,
}


@dataclass
class Detection:
    cls: str
    conf: float
    bbox: Sequence[float]  # x1, y1, x2, y2 in pixels

    def centre_norm(self, frame_w: int, frame_h: int):
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2 / frame_w, (y1 + y2) / 2 / frame_h)


@dataclass
class SensorReading:
    smoke: float
    temperature: float
    timestamp: float  # engine clock seconds


@dataclass
class Transition:
    old: State
    new: State
    timestamp: float
    reason: str
    best: Optional[Detection]


@dataclass
class EngineResult:
    state: State
    transition: Optional[Transition]
    strong_hits: int
    possible_hits: int
    sensors_elevated: bool
    best: Optional[Detection]
    reason: str


@dataclass
class _Hit:
    t: float
    conf: float
    det: Detection


class DecisionEngine:
    def __init__(self, cfg: dict, clock=None):
        t = cfg.get("temporal", {})
        d = cfg.get("detection", {})
        s = cfg.get("sensors", {})
        z = cfg.get("zone", {}) or {}

        self.classes = set(d.get("classes", ["fire", "smoke"]))
        self.min_conf = float(d.get("min_conf", 0.25))

        self.window = float(t.get("window_seconds", 3.0))
        self.warning_conf = float(t.get("warning_conf", 0.35))
        self.warning_min_hits = int(t.get("warning_min_hits", 3))
        self.confirm_conf = float(t.get("confirm_conf", 0.55))
        self.confirm_min_hits = int(t.get("confirm_min_hits", 10))
        self.confirm_min_seconds = float(t.get("confirm_min_seconds", 2.0))
        self.clear_conf = float(t.get("clear_conf", 0.25))
        self.clear_seconds = float(t.get("clear_seconds", 4.0))
        self.recovery_seconds = float(t.get("recovery_seconds", 10.0))

        self.sensors_enabled = bool(s.get("enabled", True))
        self.smoke_elevated = float(s.get("smoke_elevated", 600))
        self.temp_elevated = float(s.get("temp_elevated_c", 45.0))
        self.sensor_stale = float(s.get("stale_after_seconds", 15))
        self.confirm_hits_elevated = int(s.get("confirm_hits_when_elevated", 6))
        self.sensor_only_seconds = float(s.get("sensor_only_warning_seconds", 5.0))

        self.roi = z.get("roi")  # [x1, y1, x2, y2] normalised or None

        self._clock = clock or time.monotonic
        self.state = State.NORMAL
        self.state_since = self._clock()
        self._hits: Deque[_Hit] = deque()
        self._last_presence: Optional[float] = None
        self._sensor: Optional[SensorReading] = None
        self._sensor_elevated_since: Optional[float] = None
        self.emergency_stop = False
        self.history: List[Transition] = []

    # ------------------------------------------------------------------ inputs
    def update_sensor(self, reading: SensorReading) -> None:
        self._sensor = reading

    def acknowledge(self) -> Optional[Transition]:
        """Operator acknowledgement: silence an active event and move to RECOVERY."""
        now = self._clock()
        if self.state in (State.WARNING, State.CONFIRMED, State.SENSOR_WARNING):
            self._hits.clear()
            self._last_presence = None
            return self._set(State.RECOVERY, now, "acknowledged by operator", None)
        return None

    def set_emergency_stop(self, on: bool) -> None:
        """Manual emergency stop: blocks any physical actuator regardless of state."""
        self.emergency_stop = on

    def reset(self) -> None:
        self.state = State.NORMAL
        self.state_since = self._clock()
        self._hits.clear()
        self._last_presence = None
        self._sensor_elevated_since = None

    # ------------------------------------------------------------------ helpers
    def _in_zone(self, det: Detection, frame_w: int, frame_h: int) -> bool:
        if not self.roi:
            return True
        cx, cy = det.centre_norm(frame_w, frame_h)
        x1, y1, x2, y2 = self.roi
        return x1 <= cx <= x2 and y1 <= cy <= y2

    def _sensors_elevated(self, now: float) -> bool:
        if not self.sensors_enabled or self._sensor is None:
            return False
        if now - self._sensor.timestamp > self.sensor_stale:
            return False  # stale -> fail safe, do not trust
        return self._sensor.smoke >= self.smoke_elevated or self._sensor.temperature >= self.temp_elevated

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._hits and self._hits[0].t < cutoff:
            self._hits.popleft()

    def _set(self, new: State, now: float, reason: str, best: Optional[Detection]) -> Transition:
        tr = Transition(self.state, new, now, reason, best)
        self.state = new
        self.state_since = now
        self.history.append(tr)
        return tr

    # ------------------------------------------------------------------ main step
    def update(self, detections: Iterable[Detection], frame_w: int = 1, frame_h: int = 1) -> EngineResult:
        now = self._clock()

        # 1. filter by class / confidence / zone, keep the best detection of the frame
        best: Optional[Detection] = None
        for det in detections:
            if det.cls not in self.classes or det.conf < self.min_conf:
                continue
            if not self._in_zone(det, frame_w, frame_h):
                continue
            if best is None or det.conf > best.conf:
                best = det

        # 2. record presence / hits
        if best is not None and best.conf >= self.clear_conf:
            self._last_presence = now
        if best is not None and best.conf >= self.warning_conf:
            self._hits.append(_Hit(now, best.conf, best))
        self._prune(now)

        possible = [h for h in self._hits if h.conf >= self.warning_conf]
        strong = [h for h in self._hits if h.conf >= self.confirm_conf]
        strong_span = (strong[-1].t - strong[0].t) if len(strong) >= 2 else 0.0

        # 3. sensor evidence
        elevated = self._sensors_elevated(now)
        if elevated:
            if self._sensor_elevated_since is None:
                self._sensor_elevated_since = now
        else:
            self._sensor_elevated_since = None
        sensor_persistent = elevated and (now - self._sensor_elevated_since) >= self.sensor_only_seconds

        need_strong = self.confirm_hits_elevated if elevated else self.confirm_min_hits
        confirmed_now = len(strong) >= need_strong and strong_span >= self.confirm_min_seconds
        warning_now = len(possible) >= self.warning_min_hits
        present = self._last_presence is not None and (now - self._last_presence) < self.clear_seconds

        # 4. state machine
        transition: Optional[Transition] = None
        reason = ""
        st = self.state

        if st == State.NORMAL:
            if confirmed_now:
                reason = f"{len(strong)} strong hits over {strong_span:.1f}s" + (" + sensors elevated" if elevated else "")
                transition = self._set(State.CONFIRMED, now, reason, best)
            elif warning_now:
                reason = f"{len(possible)} possible hits in {self.window:.0f}s window"
                transition = self._set(State.WARNING, now, reason, best)
            elif sensor_persistent:
                reason = "sensors elevated with no visual target"
                transition = self._set(State.SENSOR_WARNING, now, reason, None)

        elif st == State.WARNING:
            if confirmed_now:
                reason = f"{len(strong)} strong hits over {strong_span:.1f}s" + (" + sensors elevated" if elevated else "")
                transition = self._set(State.CONFIRMED, now, reason, best)
            elif not present and not possible:
                reason = f"no target for {self.clear_seconds:.0f}s"
                transition = self._set(State.NORMAL, now, reason, None)

        elif st == State.CONFIRMED:
            if not present:
                reason = f"no target for {self.clear_seconds:.0f}s"
                transition = self._set(State.RECOVERY, now, reason, None)

        elif st == State.RECOVERY:
            if confirmed_now or (present and warning_now):
                reason = "target re-appeared during recovery"
                transition = self._set(State.CONFIRMED, now, reason, best)
            elif (now - self.state_since) >= self.recovery_seconds and not present:
                reason = f"stable for {self.recovery_seconds:.0f}s"
                transition = self._set(State.NORMAL, now, reason, None)

        elif st == State.SENSOR_WARNING:
            if confirmed_now:
                reason = "visual confirmation while sensors elevated"
                transition = self._set(State.CONFIRMED, now, reason, best)
            elif warning_now:
                reason = "possible visual target while sensors elevated"
                transition = self._set(State.WARNING, now, reason, best)
            elif not elevated:
                reason = "sensors returned to normal"
                transition = self._set(State.NORMAL, now, reason, None)

        if not reason:
            reason = f"strong={len(strong)}/{need_strong} possible={len(possible)}/{self.warning_min_hits}"

        return EngineResult(
            state=self.state,
            transition=transition,
            strong_hits=len(strong),
            possible_hits=len(possible),
            sensors_elevated=elevated,
            best=best,
            reason=reason,
        )

    # ------------------------------------------------------------------ outputs
    @property
    def actuator_allowed(self) -> bool:
        """Physical action only after CONFIRMED and never while the emergency stop is set."""
        return self.state == State.CONFIRMED and not self.emergency_stop

    def snapshot(self) -> dict:
        now = self._clock()
        return {
            "state": self.state.value,
            "severity": SEVERITY[self.state],
            "state_for_seconds": round(now - self.state_since, 1),
            "sensors_elevated": self._sensors_elevated(now),
            "emergency_stop": self.emergency_stop,
        }
