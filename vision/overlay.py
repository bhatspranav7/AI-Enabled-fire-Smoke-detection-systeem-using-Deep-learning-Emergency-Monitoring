"""Detection overlay: boxes + confidence, state banner, FPS/latency, sensor strip."""
from __future__ import annotations

from typing import Iterable, Optional

import cv2
import numpy as np

STATE_COLORS = {  # BGR
    "NORMAL": (60, 180, 75),
    "WARNING": (0, 165, 255),
    "CONFIRMED": (30, 30, 220),
    "RECOVERY": (200, 160, 40),
    "SENSOR_WARNING": (0, 200, 230),
    "CAMERA LOST": (120, 120, 120),
}
CLASS_COLORS = {"fire": (0, 60, 255), "smoke": (230, 200, 90)}


def draw_overlay(frame: np.ndarray, detections: Iterable, state: str, fps: float, latency_ms: float,
                 reason: str = "", sensor: Optional[dict] = None, roi=None, estop: bool = False,
                 device_name: str = "") -> np.ndarray:
    out = frame
    h, w = out.shape[:2]

    # zone of interest
    if roi:
        x1, y1, x2, y2 = int(roi[0] * w), int(roi[1] * h), int(roi[2] * w), int(roi[3] * h)
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 255, 255), 1)

    # detections
    for d in detections:
        x1, y1, x2, y2 = map(int, d.bbox)
        color = CLASS_COLORS.get(d.cls, (255, 255, 255))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{d.cls} {d.conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(out, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        cv2.putText(out, label, (x1 + 3, max(th + 2, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # state banner
    color = STATE_COLORS.get(state, (200, 200, 200))
    cv2.rectangle(out, (0, 0), (w, 44), color, -1)
    cv2.putText(out, state, (12, 31), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    if reason:
        cv2.putText(out, reason[:70], (190, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    if state == "CONFIRMED":
        cv2.rectangle(out, (0, 0), (w - 1, h - 1), color, 8)

    # bottom strip: fps, latency, sensors, estop
    cv2.rectangle(out, (0, h - 30), (w, h), (0, 0, 0), -1)
    txt = f"{device_name}  FPS {fps:4.1f}  latency {latency_ms:5.1f} ms"
    if sensor:
        txt += f"   smoke {sensor.get('smoke', '-')}   temp {sensor.get('temperature', '-')} C"
        if sensor.get("stale"):
            txt += " (stale)"
    cv2.putText(out, txt, (10, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    if estop:
        cv2.putText(out, "EMERGENCY STOP", (w - 230, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return out


def camera_lost_frame(w: int = 1280, h: int = 720, seconds: float = 0.0) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.putText(frame, "CAMERA LOST - reconnecting", (int(w * 0.25), h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    cv2.putText(frame, f"{seconds:.0f}s", (int(w * 0.25), h // 2 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    return frame
