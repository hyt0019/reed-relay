from types import SimpleNamespace

import numpy as np
import pytest

from reed_relay.capture import AudioWindow, SystemAudioCapture, loopback_devices
from reed_relay.core.tuning import detect_frequency


DEVICE = {"index": 2, "name": "Headphones [Loopback]", "rate": 48000, "channels": 2}


class FakeStream:
    def __init__(self):
        self.active = True
        self.closed = False
        self.fail_stop = False

    def is_active(self): return self.active

    def stop_stream(self):
        self.active = False
        if self.fail_stop: raise OSError("unplugged")

    def close(self): self.closed = True


class FakeManager:
    def __init__(self):
        self.terminated = False
        self.info = {"index": 2, "name": DEVICE["name"], "defaultSampleRate": 48000,
                     "maxInputChannels": 2, "isLoopbackDevice": True}
        self.stream = FakeStream()
        self.fail_open = False

    def get_host_api_info_by_type(self, host): return {"index": 1}
    def get_default_wasapi_loopback(self): return self.info
    def get_loopback_device_info_generator(self): return iter([self.info])
    def get_device_info_by_index(self, index): return self.info
    def terminate(self): self.terminated = True

    def open(self, **kwargs):
        self.options = kwargs
        if self.fail_open: raise OSError("device unavailable")
        return self.stream


def module_for(manager):
    return SimpleNamespace(PyAudio=lambda: manager, paWASAPI=13, paFloat32=1, paContinue=0, paAbort=2)


@pytest.mark.parametrize("rate", [44100, 48000, 96000])
def test_arbitrary_stereo_chunks_keep_pitch_and_bounded_buffer(rate):
    buffer = AudioWindow(rate)
    signal = .15 * np.sin(2*np.pi*440*np.arange(rate)/rate)
    stereo = np.column_stack((signal, -signal))
    for chunk in np.array_split(stereo, 73): buffer.push(chunk)
    assert buffer.windows.qsize() <= 2
    assert len(buffer.pending) < buffer.size
    assert detect_frequency(buffer.latest(), rate) == pytest.approx(440, abs=1)
    assert buffer.latest() is None
    buffer.push(np.empty((0, 2)))


def test_device_enumeration_marks_default_and_releases_manager():
    manager = FakeManager()
    devices = loopback_devices(module_for(manager))
    assert devices[0]["default"] is True
    assert devices[0]["rate"] == 48000
    assert "系统默认" in devices[0]["label"]
    assert manager.terminated


def test_callback_uses_device_rate_and_stop_releases_even_after_unplug():
    manager = FakeManager()
    capture = SystemAudioCapture(DEVICE, module_for(manager))
    capture.start()
    assert manager.options["input_device_index"] == 2
    assert manager.options["rate"] == 48000
    assert manager.options["channels"] == 2
    callback = manager.options["stream_callback"]
    tone = .1*np.sin(2*np.pi*440*np.arange(12000)/48000)
    callback(np.column_stack((tone,tone)).astype(np.float32).tobytes(),12000,{},0)
    assert detect_frequency(capture.latest(), capture.rate) == pytest.approx(440, abs=1)
    manager.stream.fail_stop = True
    with pytest.raises(OSError): capture.stop()
    assert manager.stream.closed and manager.terminated
    capture.stop()


def test_open_failure_and_changed_device_do_not_leave_capture_open():
    for changed in (True, False):
        manager = FakeManager()
        if changed: manager.info["name"] = "Another device"
        else: manager.fail_open = True
        capture = SystemAudioCapture(DEVICE, module_for(manager))
        with pytest.raises((RuntimeError, OSError)): capture.start()
        assert manager.terminated
        assert capture.manager is None and capture.stream is None


def test_backend_switch_silence_and_device_failure_clear_measurement(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from reed_relay.backend import Backend
    import reed_relay.capture as capture_module
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR", str(tmp_path))
    instances = []

    class FakeCapture:
        rate = 48000
        def __init__(self, device):
            self.closed = False
            self.samples = .1*np.sin(2*np.pi*440*np.arange(12000)/self.rate)
            self.failed = False
            instances.append(self)
        def start(self): pass
        def latest(self):
            if self.failed: raise OSError("unplugged")
            return self.samples
        def stop(self): self.closed = True

    monkeypatch.setattr(capture_module, "loopback_devices", lambda: [DEVICE])
    monkeypatch.setattr(capture_module, "SystemAudioCapture", FakeCapture)
    backend = Backend("player", no_hotkeys=True)
    backend.refreshAudioDevices()
    backend.toggleTuning()
    assert backend.listening
    backend._read_tuning()
    assert backend.tuning["pitch"] == 69 and backend.captureLevel > 0
    instances[-1].samples = None
    backend._last_audio_time = 0
    backend._read_tuning()
    assert backend.tuning["frequency"] == 0 and backend.captureLevel == 0
    backend.setCaptureDevice(0)
    assert instances[-1].closed and not backend.listening
    backend.toggleTuning()
    instances[-1].failed = True
    backend._read_tuning()
    assert not backend.listening and instances[-1].closed
    assert "中断" in backend.captureStatus
    backend.toggleTuning()
    backend.setCaptureSource("microphone")
    assert instances[-1].closed and not backend.listening
    backend.close()
