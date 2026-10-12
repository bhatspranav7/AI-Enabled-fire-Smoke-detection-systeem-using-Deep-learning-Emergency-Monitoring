"""Camera / video source wrapper with automatic reconnect (PDF 18.2: camera disconnect).

Accepts: webcam index (0, 1, ...), a video file path, an RTSP/HTTP URL, or a folder of
images (cycled, useful for demos without a live fire).
"""
from __future__ import annotations

import pathlib
import time
from typing import Optional, Tuple

import cv2
import numpy as np

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class Camera:
    def __init__(self, source, width: int = 1280, height: int = 720, reconnect_seconds: float = 3.0,
                 loop_video: bool = True, image_seconds: float = 2.0):
        self.source = source
        self.width, self.height = width, height
        self.reconnect_seconds = reconnect_seconds
        self.loop_video = loop_video
        self.image_seconds = image_seconds
        self.cap: Optional[cv2.VideoCapture] = None
        self.kind = "webcam"
        self._images: list[pathlib.Path] = []
        self._img_idx = 0
        self._img_shown_at = 0.0
        self._last_frame: Optional[np.ndarray] = None
        self._disconnected_since: Optional[float] = None
        self._classify()
        self.open()

    # ----------------------------------------------------------------- setup
    def _classify(self) -> None:
        s = self.source
        if isinstance(s, int) or (isinstance(s, str) and s.isdigit()):
            self.source = int(s)
            self.kind = "webcam"
        elif isinstance(s, str) and s.lower().startswith(("rtsp://", "http://", "https://")):
            self.kind = "stream"
        elif isinstance(s, str) and pathlib.Path(s).is_dir():
            self.kind = "images"
            self._images = sorted(p for p in pathlib.Path(s).iterdir() if p.suffix.lower() in IMG_EXT)
        else:
            self.kind = "video"

    def open(self) -> bool:
        if self.kind == "images":
            return bool(self._images)
        if self.cap is not None:
            self.cap.release()
        if self.kind == "webcam":
            # CAP_DSHOW opens much faster on Windows; fall back to default backend elsewhere
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.source)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        else:
            self.cap = cv2.VideoCapture(self.source)
        ok = self.cap.isOpened()
        if ok:
            self._disconnected_since = None
        return ok

    @property
    def connected(self) -> bool:
        if self.kind == "images":
            return bool(self._images)
        return self.cap is not None and self.cap.isOpened() and self._disconnected_since is None

    # ----------------------------------------------------------------- frames
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns (ok, frame). On a lost source, retries every reconnect_seconds and
        returns (False, None) meanwhile so the caller can show a 'camera lost' state."""
        if self.kind == "images":
            now = time.monotonic()
            if self._last_frame is None or now - self._img_shown_at >= self.image_seconds:
                p = self._images[self._img_idx % len(self._images)]
                self._img_idx += 1
                self._img_shown_at = now
                self._last_frame = cv2.imread(str(p))
            return self._last_frame is not None, self._last_frame

        if self.cap is None or not self.cap.isOpened():
            return self._handle_loss()
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self._disconnected_since = None
            return True, frame
        if self.kind == "video" and self.loop_video:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if ok:
                return True, frame
        return self._handle_loss()

    def _handle_loss(self) -> Tuple[bool, None]:
        now = time.monotonic()
        if self._disconnected_since is None:
            self._disconnected_since = now
            self._last_retry = now
        elif now - self._last_retry >= self.reconnect_seconds:
            self._last_retry = now
            self.open()
        return False, None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
