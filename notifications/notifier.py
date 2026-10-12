"""Notification service (PDF 14.1 / 23). Channels: console, log file, Telegram, email.

Secrets come from environment variables / .env (never from the YAML). Every channel
reports success/failure so the backend can store it in the notifications table and the
'notification failure' integration test (PDF 18.2) is observable.
"""
from __future__ import annotations

import os
import pathlib
import smtplib
import threading
import time
from email.message import EmailMessage
from typing import Callable, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_dotenv(path: pathlib.Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Notifier:
    def __init__(self, cfg: dict, on_result: Optional[Callable[[str, str, str], None]] = None):
        _load_dotenv()
        self.cfg = cfg or {}
        self.channels = self.cfg.get("channels", {})
        self.title = self.cfg.get("message", {}).get("title", "FIRE/SMOKE ALERT")
        self.include_evidence = self.cfg.get("message", {}).get("include_evidence", True)
        self.on_result = on_result  # callback(channel, status, detail)
        self._last_sent: Dict[str, float] = {}

    # ---------------------------------------------------------------- public
    def send(self, state: str, device: str, location: str, reason: str, confidence: Optional[float],
             cls: Optional[str], evidence_path: Optional[str], cooldown: float = 60.0) -> List[dict]:
        """Fire-and-forget on a worker thread so the inference loop is never blocked."""
        key = f"{device}:{state}"
        now = time.time()
        if now - self._last_sent.get(key, 0) < cooldown:
            return [{"channel": "all", "status": "skipped", "detail": "cooldown"}]
        self._last_sent[key] = now

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (f"{self.title}: {state}\nDevice: {device} ({location})\nTime: {ts}\n"
                f"Reason: {reason}\n"
                + (f"Detection: {cls} {confidence:.2f}\n" if cls and confidence is not None else "")
                + (f"Evidence: {evidence_path}\n" if evidence_path else ""))
        results: List[dict] = []
        threading.Thread(target=self._dispatch, args=(text, evidence_path, results), daemon=True).start()
        return results

    # ---------------------------------------------------------------- channels
    def _dispatch(self, text: str, evidence_path: Optional[str], results: List[dict]) -> None:
        for name, fn in (("console", self._console), ("log_file", self._log_file),
                         ("telegram", self._telegram), ("email", self._email)):
            ch = self.channels.get(name, {})
            if not ch.get("enabled"):
                continue
            try:
                detail = fn(ch, text, evidence_path)
                status = "sent"
            except Exception as e:  # noqa: BLE001 - we want every failure recorded, never raised
                status, detail = "failed", f"{type(e).__name__}: {e}"
            results.append({"channel": name, "status": status, "detail": detail})
            if self.on_result:
                try:
                    self.on_result(name, status, detail)
                except Exception:
                    pass

    def _console(self, ch, text, evidence):
        print("\n" + "=" * 60 + "\n" + text + "=" * 60 + "\n", flush=True)
        return "printed"

    def _log_file(self, ch, text, evidence):
        p = ROOT / ch.get("path", "logs/notifications.log")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(text.replace("\n", " | ") + "\n")
        return str(p)

    def _telegram(self, ch, text, evidence):
        import requests

        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat:
            raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")
        timeout = ch.get("timeout_seconds", 5)
        if self.include_evidence and evidence and pathlib.Path(evidence).exists():
            with open(evidence, "rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                  data={"chat_id": chat, "caption": text[:1000]}, files={"photo": f}, timeout=timeout)
        else:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              data={"chat_id": chat, "text": text}, timeout=timeout)
        r.raise_for_status()
        return f"telegram {r.status_code}"

    def _email(self, ch, text, evidence):
        host, port = os.environ.get("SMTP_HOST"), int(os.environ.get("SMTP_PORT", "587"))
        user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
        sender = os.environ.get("SMTP_FROM") or user
        to = ch.get("to") or []
        if not (host and user and pw and to):
            raise RuntimeError("SMTP_* not set in .env or no recipients in notification_config.yaml")
        msg = EmailMessage()
        msg["Subject"] = text.splitlines()[0]
        msg["From"], msg["To"] = sender, ", ".join(to)
        msg.set_content(text)
        if self.include_evidence and evidence and pathlib.Path(evidence).exists():
            msg.add_attachment(pathlib.Path(evidence).read_bytes(), maintype="image", subtype="jpeg",
                               filename=pathlib.Path(evidence).name)
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return f"email to {len(to)} recipient(s)"
