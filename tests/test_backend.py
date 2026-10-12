"""API tests for the FastAPI backend using an isolated temporary database."""
import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    import backend.app as appmod

    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_sensor_and_status(client):
    r = client.post("/sensors", json={"device_id": "esp32-01", "smoke": 300, "temperature": 28})
    assert r.json()["ok"]
    s = client.get("/status").json()
    assert s["sensor"]["smoke"] == 300
    assert any(d["id"] == "esp32-01" for d in client.get("/devices").json())


def test_detections_update_state(client):
    client.post("/detections", json={"device_id": "cam01", "state": "WARNING", "reason": "x",
                                     "detections": [{"cls": "fire", "conf": 0.8, "bbox": [1, 2, 3, 4]}], "fps": 10, "latency_ms": 50})
    s = client.get("/status").json()
    assert s["overall_state"] == "WARNING"
    assert s["latest_detections"][0]["class"] == "fire"
    assert client.get("/devices/cam01").json()["live_state"]["state"] == "WARNING"


def test_event_lifecycle_and_ack(client):
    eid = client.post("/events", json={"device_id": "cam01", "severity": 3, "state": "CONFIRMED", "reason": "r"}).json()["id"]
    assert client.get(f"/events/{eid}").json()["acknowledged"] == 0
    assert client.get("/status").json()["open_events"][0]["id"] == eid
    r = client.post(f"/events/{eid}/ack")
    assert r.json()["event"]["acknowledged"] == 1
    cmds = client.get("/devices/cam01/commands").json()["commands"]
    assert cmds and cmds[0]["type"] == "ack" and cmds[0]["event_id"] == eid
    assert client.get("/devices/cam01/commands").json()["commands"] == []  # popped
    client.post(f"/events/{eid}/end", json={"peak_confidence": 0.9, "peak_class": "fire"})
    ev = client.get(f"/events/{eid}").json()
    assert ev["end_time"] is not None and ev["peak_class"] == "fire"
    assert client.get("/status").json()["open_events"] == []


def test_unknown_event_404(client):
    assert client.get("/events/999").status_code == 404
    assert client.post("/events/999/ack").status_code == 404


def test_estop_relayed(client):
    client.post("/detections", json={"device_id": "cam01", "state": "NORMAL", "detections": []})
    assert client.post("/control/estop", json={"on": True}).json()["on"] is True
    c = client.get("/devices/cam01/commands").json()
    assert c["emergency_stop"] is True and c["commands"][0]["type"] == "estop"


def test_frames_and_live_jpg(client):
    assert client.get("/live/cam01.jpg").status_code == 404
    client.post("/frames/cam01", content=b"\xff\xd8fakejpeg", headers={"Content-Type": "image/jpeg"})
    r = client.get("/live/cam01.jpg")
    assert r.status_code == 200 and r.content.startswith(b"\xff\xd8")


def test_notifications(client):
    client.post("/notifications", json={"event_id": None, "channel": "console", "status": "sent"})
    assert client.get("/notifications").json()[0]["channel"] == "console"
