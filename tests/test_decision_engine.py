"""Unit tests for the temporal decision engine (run: pytest tests/ -q)."""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decision_engine import DecisionEngine, Detection, SensorReading, State  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, dt=0.1):
        self.t += dt


def make_engine():
    cfg = yaml.safe_load((ROOT / "configs" / "thresholds.yaml").read_text())
    clock = FakeClock()
    return DecisionEngine(cfg, clock=clock), clock


def fire(conf):
    return [Detection("fire", conf, (100, 100, 200, 200))]


def feed(engine, clock, dets, frames, dt=0.1):
    res = None
    for _ in range(frames):
        res = engine.update(dets, 640, 480)
        clock.tick(dt)
    return res


def test_starts_normal():
    eng, _ = make_engine()
    assert eng.state == State.NORMAL


def test_single_frame_does_not_trigger():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.95), 1)
    feed(eng, clock, [], 5)
    assert eng.state == State.NORMAL


def test_possible_hits_enter_warning_not_confirmed():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.40), 5)  # above warning_conf, below confirm_conf
    assert eng.state == State.WARNING


def test_persistent_strong_hits_confirm():
    eng, clock = make_engine()
    res = feed(eng, clock, fire(0.9), 25)  # 2.5 s of strong hits at 10 fps
    assert eng.state == State.CONFIRMED
    assert any(t.new == State.CONFIRMED for t in eng.history)
    assert res.best.cls == "fire"


def test_strong_hits_too_short_in_time_stay_warning():
    eng, clock = make_engine()
    # 12 strong hits but only 0.12 s apart -> span 0.11s < confirm_min_seconds
    feed(eng, clock, fire(0.9), 12, dt=0.01)
    assert eng.state == State.WARNING


def test_low_confidence_noise_ignored():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.20), 50)  # below min_conf
    assert eng.state == State.NORMAL


def test_other_classes_ignored():
    eng, clock = make_engine()
    feed(eng, clock, [Detection("person", 0.99, (0, 0, 50, 50))], 50)
    assert eng.state == State.NORMAL


def test_confirmed_then_recovery_then_normal():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.9), 25)
    assert eng.state == State.CONFIRMED
    feed(eng, clock, [], 45)  # 4.5 s with nothing -> RECOVERY
    assert eng.state == State.RECOVERY
    feed(eng, clock, [], 110)  # > recovery_seconds -> NORMAL
    assert eng.state == State.NORMAL


def test_reappearance_during_recovery_reconfirms():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.9), 25)
    feed(eng, clock, [], 45)
    assert eng.state == State.RECOVERY
    feed(eng, clock, fire(0.9), 25)
    assert eng.state == State.CONFIRMED


def test_hysteresis_low_conf_keeps_confirmed():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.9), 25)
    # drops to 0.3: below warning_conf but above clear_conf -> still 'present', stays CONFIRMED
    feed(eng, clock, fire(0.30), 60)
    assert eng.state == State.CONFIRMED


def test_sensor_fusion_lowers_confirm_bar():
    eng, clock = make_engine()
    eng.update_sensor(SensorReading(smoke=900, temperature=30, timestamp=clock()))
    feed(eng, clock, fire(0.6), 7, dt=0.35)  # 7 strong hits over 2.1 s: < 10 normally, >= 6 when elevated
    assert eng.state == State.CONFIRMED


def test_stale_sensor_is_ignored():
    eng, clock = make_engine()
    eng.update_sensor(SensorReading(smoke=900, temperature=30, timestamp=clock()))
    clock.tick(60)  # reading is now stale
    feed(eng, clock, fire(0.6), 7, dt=0.35)
    assert eng.state == State.WARNING  # elevated bar not applied


def test_sensor_only_persistent_gives_sensor_warning():
    eng, clock = make_engine()
    for _ in range(70):
        eng.update_sensor(SensorReading(smoke=900, temperature=30, timestamp=clock()))
        eng.update([], 640, 480)
        clock.tick(0.1)
    assert eng.state == State.SENSOR_WARNING
    # sensors recover -> NORMAL
    eng.update_sensor(SensorReading(smoke=100, temperature=25, timestamp=clock()))
    eng.update([], 640, 480)
    assert eng.state == State.NORMAL


def test_zone_filters_outside_detections():
    cfg = {"temporal": {}, "zone": {"roi": [0.5, 0.0, 1.0, 1.0]}}
    clock = FakeClock()
    eng = DecisionEngine(cfg, clock=clock)
    left = [Detection("fire", 0.9, (10, 10, 100, 100))]  # centre x ~ 0.08 -> outside
    feed(eng, clock, left, 25)
    assert eng.state == State.NORMAL
    right = [Detection("fire", 0.9, (500, 10, 600, 100))]  # centre x ~ 0.86 -> inside
    feed(eng, clock, right, 25)
    assert eng.state == State.CONFIRMED


def test_acknowledge_and_emergency_stop():
    eng, clock = make_engine()
    feed(eng, clock, fire(0.9), 25)
    assert eng.actuator_allowed
    eng.set_emergency_stop(True)
    assert not eng.actuator_allowed
    tr = eng.acknowledge()
    assert tr.new == State.RECOVERY
    assert eng.state == State.RECOVERY
