"""ESP32 stand-in: posts smoke/gas + temperature readings to the backend (PDF 12.2 payload).

Lets the sensor-fusion path be demonstrated before the hardware is wired. Press keys in
this terminal to inject scenarios:

    n  normal readings          s  smoke rising (gas sensor spikes)
    h  heat rising              b  both (smoke + heat)          x  stop sending (sensor disconnect test)

    python iot/sensor_simulator.py --backend http://127.0.0.1:8000 --interval 1
"""
from __future__ import annotations

import argparse
import random
import sys
import threading
import time

import requests

MODES = {"n": "normal", "s": "smoke", "h": "heat", "b": "both", "x": "disconnected"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:8000")
    ap.add_argument("--device", default="esp32-01")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--mode", default="n", choices=list(MODES))
    args = ap.parse_args()

    state = {"mode": args.mode}

    def keys():
        if sys.platform == "win32":
            import msvcrt

            while True:
                ch = msvcrt.getch().decode(errors="ignore").lower()
                if ch in MODES:
                    state["mode"] = ch
                    print(f"\n[sim] mode -> {MODES[ch]}", flush=True)
        else:
            for line in sys.stdin:
                ch = line.strip().lower()[:1]
                if ch in MODES:
                    state["mode"] = ch
                    print(f"[sim] mode -> {MODES[ch]}", flush=True)

    threading.Thread(target=keys, daemon=True).start()

    try:
        requests.post(f"{args.backend}/devices", json={"id": args.device, "name": "ESP32 sensor node",
                                                        "location": "Project Lab - Bench A", "kind": "sensor"}, timeout=2)
    except Exception as e:
        print("[sim] backend not reachable yet:", e)

    smoke, temp = 180.0, 26.0
    print(f"[sim] sending to {args.backend} every {args.interval}s. keys: n normal | s smoke | h heat | b both | x disconnect")
    while True:
        m = state["mode"]
        target_s = {"n": 180, "s": 820, "h": 200, "b": 850, "x": 180}[m]
        target_t = {"n": 26, "s": 28, "h": 62, "b": 60, "x": 26}[m]
        smoke += (target_s - smoke) * 0.25 + random.uniform(-8, 8)
        temp += (target_t - temp) * 0.2 + random.uniform(-0.3, 0.3)
        payload = {"device_id": args.device, "smoke": round(smoke, 1), "temperature": round(temp, 1), "timestamp": time.time()}
        if m == "x":
            print(f"\r[sim] DISCONNECTED (not sending)        ", end="", flush=True)
        else:
            try:
                requests.post(f"{args.backend}/sensors", json=payload, timeout=2)
                print(f"\r[sim] {MODES[m]:12s} smoke={payload['smoke']:6.1f} temp={payload['temperature']:5.1f}C   ", end="", flush=True)
            except Exception as e:
                print(f"\r[sim] post failed: {e}        ", end="", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
