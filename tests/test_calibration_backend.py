"""Exercise the complete wizard without recording hardware or sending game input."""
import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
import reed_relay.backend as module
import reed_relay.capture as capture_module
from reed_relay.core.profile import Profile


@pytest.fixture
def rig(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    state = {"now":0., "held":set(), "focus":True, "alive":True, "ready":True}

    class FakeHotkeys:
        ready = False
        def __init__(self, *args): self.bindings = {}
        def start(self, bindings):
            self.bindings = dict(bindings)
            self.ready = state["ready"]
        def close(self): self.ready = False

    class FakeCapture:
        rate = 48000
        def __init__(self, device): self.stopped = False
        def start(self): pass
        def latest(self):
            if state.get("error"): raise OSError("device disconnected")
            return state.pop("audio", None)
        def stop(self): self.stopped = True

    monkeypatch.setenv("REED_RELAY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(module, "Hotkeys", FakeHotkeys)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: state["now"]))
    monkeypatch.setattr(module, "held_controls", lambda _: state["held"])
    monkeypatch.setattr(module, "window_alive", lambda _: state["alive"])
    monkeypatch.setattr(module, "focus_guard", lambda _: lambda: state["focus"])
    monkeypatch.setattr(module, "monitor_name", lambda _: "test-display")
    monkeypatch.setattr(capture_module, "SystemAudioCapture", FakeCapture)
    backend = module.Backend("player", no_hotkeys=True)
    backend._no_hotkeys = False
    backend._windows = [{"handle":123, "pid":456, "title":"Test game"}]
    backend._capture_devices, backend._capture_device = [{"name":"test"}], 0
    backend._profile.save(tmp_path/"profile.json")

    def tick(now, held=(), sample=None):
        state.update(now=now, held=set(held))
        backend._tick_calibration(sample)

    def start(profile=None):
        backend.startCalibration(json.dumps((profile or backend._profile).to_dict()), 0, "top-left")
        tick(0)
        tick(4)
        tick(4.8)
        return backend._loopback

    def finish():
        now = state["now"]
        while backend.calibrationActive:
            guide = backend._calibration
            step = guide.step
            pitch = [62,64,66,67,69,71,73,74][step.base]+sum([-12,1,12][i] for i in step.modifiers)
            tick(now, guide.expected)
            for delta in (.5,.75,1.):
                tick(now+delta, guide.expected, {"frequency":440, "pitch":pitch, "cents":0})
            assert guide.phase == "release"
            now += 1.1
            tick(now)
            now += .8
            tick(now)

    yield SimpleNamespace(backend=backend, state=state, tick=tick, start=start, finish=finish, path=tmp_path)
    backend.close()


def test_completion_saves_draft_keys_measured_pitches_and_old_backup(rig):
    backend = rig.backend
    draft = Profile(keys=list("ASDFGHJK"), hotkeys={"toggle":"CTRL+F8", "previous":"CTRL+F6", "next":"CTRL+F7", "emergency":"CTRL+F10"})
    capture = rig.start(draft)
    rig.finish()
    saved = Profile.load(rig.path/"profile.json")
    assert saved.calibrated and saved.pitches == [62,64,66,67,69,71,73,74]
    assert saved.keys == list("ASDFGHJK") and saved.hotkeys == draft.hotkeys
    assert Profile.load(rig.path/"profile.before-calibration.json").to_dict() == Profile().to_dict()
    assert capture.stopped and not backend.listening and not backend._calibration_timer.isActive()
    assert backend.calibration["phase"] == "done" and backend.calibration["visible"]
    backend.loadDemo()
    backend._on_hotkey("toggle")  # Completion screen must not accidentally start a song.
    assert not backend.engine.running
    backend._on_hotkey("emergency")
    assert not backend.calibration["visible"] and backend.hotkeys.bindings == saved.hotkeys


def test_cancel_discards_partial_results_and_routes_hotkeys(rig):
    before = (rig.path/"profile.json").read_bytes()
    capture = rig.start()
    backend = rig.backend
    backend._on_hotkey("toggle")
    assert backend.calibration["paused"]
    backend._on_hotkey("toggle")
    assert not backend.calibration["paused"]
    backend._on_hotkey("emergency")
    assert backend.calibration["phase"] == "cancelled"
    assert capture.stopped and not backend.listening
    assert (rig.path/"profile.json").read_bytes() == before
    assert not (rig.path/"profile.before-calibration.json").exists()


def test_save_failure_keeps_original_configuration(rig, monkeypatch):
    before = (rig.path/"profile.json").read_bytes()
    original_save = Profile.save
    def deny_current(self, path):
        if path.name == "profile.json": raise OSError("disk write denied")
        original_save(self, path)
    monkeypatch.setattr(Profile, "save", deny_current)
    capture = rig.start()
    rig.finish()
    assert rig.backend.calibration["phase"] == "failed"
    assert "disk write denied" in rig.backend.message
    assert capture.stopped and not rig.backend._profile.calibrated
    assert (rig.path/"profile.json").read_bytes() == before


@pytest.mark.parametrize("failure", ["hotkeys", "device", "window"])
def test_hardware_or_hotkey_failure_cleans_up_without_saving(rig, failure):
    before = (rig.path/"profile.json").read_bytes()
    capture = rig.start()
    if failure == "hotkeys": rig.backend.hotkeys.ready = False
    if failure == "window": rig.state["alive"] = False
    if failure == "device":
        rig.state["error"] = True
        rig.backend._read_tuning()
    else: rig.tick(5)
    assert rig.backend.calibration["phase"] == "failed"
    assert capture.stopped and not rig.backend.listening
    assert (rig.path/"profile.json").read_bytes() == before


def test_hotkey_registration_timeout_cannot_enter_guide(rig):
    rig.state["ready"] = False
    rig.backend.startCalibration(json.dumps(Profile().to_dict()), 0, "top-right")
    capture = rig.backend._loopback
    rig.tick(4)
    assert rig.backend.calibration["phase"] == "failed" and capture.stopped
    assert "热键未就绪" in rig.backend.message


def test_fresh_audio_uses_draft_reference_and_stale_audio_resets_confirmation(rig, monkeypatch):
    rig.start(Profile(reference_hz=442))
    rig.tick(5, {"Z"})
    rig.state.update(now=5.5, audio=np.ones(12000)*.2)
    monkeypatch.setattr(module, "detect_frequency", lambda *args: 442)
    rig.backend._read_tuning()
    guide = rig.backend._calibration
    assert guide.samples == [(69,0.,5.5)]
    rig.state["now"] = 7
    rig.backend._read_tuning()
    assert not guide.samples and not guide.values
    rig.state["focus"] = False
    rig.tick(7.5, {"Z"}, {"frequency":442,"pitch":69,"cents":0})
    assert guide.phase == "release" and not guide.values


def test_gui_reload_and_save_does_not_reenable_skipped_combo(rig):
    from pathlib import Path
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
    from PySide6.QtQuickControls2 import QQuickStyle
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", rig.backend)
    engine.rootContext().setContextProperty("initialPage", "settings")
    engine.load(QUrl.fromLocalFile(str(Path(module.__file__).parent/"ui/Main.qml")))
    assert engine.rootObjects()
    root = engine.rootObjects()[0]
    rig.backend._profile.combinations = [[],[0],[1],[2],[1,2]]
    rig.backend.profileChanged.emit()
    expr = QQmlExpression(engine.rootContext(), root, "JSON.stringify(profileDraft())")
    result, undefined = expr.evaluate()
    assert not undefined and not expr.hasError()
    rig.backend.saveProfile(result)
    assert [0,1] not in rig.backend._profile.combinations
    assert [1,2] in rig.backend._profile.combinations
    root.hide()
