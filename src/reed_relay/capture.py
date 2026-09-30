"""Windows output loopback for the tuner; audio stays in bounded memory."""
from __future__ import annotations

import queue
import time
import numpy as np


def _module():
    try:
        import pyaudiowpatch
        return pyaudiowpatch
    except ImportError as exc:
        raise RuntimeError("电脑声音采集组件缺失，请运行 setup.ps1 更新依赖") from exc


def loopback_devices(module=None):
    module = module or _module()
    manager = module.PyAudio()
    try:
        manager.get_host_api_info_by_type(module.paWASAPI)
        try:
            default = manager.get_default_wasapi_loopback()["index"]
        except (OSError, LookupError):
            default = None
        devices = []
        for info in manager.get_loopback_device_info_generator():
            if info["maxInputChannels"] <= 0:
                continue
            name = info["name"].removesuffix(" [Loopback]")
            devices.append({"index": int(info["index"]), "name": info["name"],
                            "label": name + ("（系统默认）" if info["index"] == default else ""),
                            "rate": int(info["defaultSampleRate"]), "channels": int(info["maxInputChannels"]),
                            "default": info["index"] == default})
        return sorted(devices, key=lambda device: not device["default"])
    finally:
        manager.terminate()


class AudioWindow:
    """Group arbitrary callbacks into quarter-second windows without backlog."""
    def __init__(self, rate):
        self.size = max(1, int(rate * .25))
        self.pending = np.empty(0, dtype=np.float32)
        self.windows = queue.Queue(maxsize=2)

    def push(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        if not len(samples):
            return
        if samples.ndim == 2:
            # An audible channel must not disappear when stereo phases cancel.
            channel = int(np.argmax(np.mean(samples * samples, axis=0)))
            samples = samples[:, channel]
        self.pending = np.concatenate((self.pending, samples))[-self.size * 2:]
        while len(self.pending) >= self.size:
            window = self.pending[:self.size].copy()
            self.pending = self.pending[self.size:]
            try:
                self.windows.put_nowait(window)
            except queue.Full:
                try:
                    self.windows.get_nowait()
                except queue.Empty:
                    pass
                self.windows.put_nowait(window)

    def latest(self):
        latest = None
        while True:
            try:
                latest = self.windows.get_nowait()
            except queue.Empty:
                return latest


class SystemAudioCapture:
    def __init__(self, device, module=None):
        self.device = dict(device)
        self.rate = int(device["rate"])
        self.buffer = AudioWindow(self.rate)
        self.module = module or _module()
        self.manager = None
        self.stream = None
        self.error = None

    def start(self):
        self.stop()
        self.buffer = AudioWindow(self.rate)
        self.error = None
        self.manager = self.module.PyAudio()
        try:
            info = self.manager.get_device_info_by_index(self.device["index"])
            if not info.get("isLoopbackDevice") or info["name"] != self.device["name"]:
                raise RuntimeError("声音设备已变化，请刷新设备后重新选择")
            self.rate = int(info["defaultSampleRate"])
            channels = int(info["maxInputChannels"])
            if self.rate <= 0 or channels <= 0:
                raise RuntimeError("所选设备无法采集，请刷新设备或选择其他输出")
            self.buffer = AudioWindow(self.rate)

            def callback(data, frames, timing, status):
                try:
                    if data:
                        samples = np.frombuffer(data, dtype=np.float32).reshape(-1, channels)
                        self.buffer.push(samples)
                    return None, self.module.paContinue
                except Exception as exc:
                    self.error = str(exc)
                    return None, self.module.paAbort

            self.stream = self.manager.open(format=self.module.paFloat32, channels=channels,
                                            rate=self.rate, input=True, input_device_index=info["index"],
                                            frames_per_buffer=max(256, self.rate // 20),
                                            stream_callback=callback)
        except Exception:
            try:
                self.stop()
            except Exception:
                pass
            raise

    def latest(self):
        if self.error:
            raise RuntimeError(f"声音采集失败：{self.error}")
        if self.stream is None or not self.stream.is_active():
            raise RuntimeError("声音采集已中断，请刷新设备后重新开始")
        return self.buffer.latest()

    def stop(self):
        stream, manager = self.stream, self.manager
        self.stream = self.manager = None
        try:
            if stream:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
        finally:
            if manager:
                manager.terminate()


def check_loopback():
    """Explicit hardware check: play a short A4 and return numbers, never audio."""
    from .core.tuning import detect_frequency
    module = _module()
    devices = loopback_devices(module)
    device = next((d for d in devices if d["default"]), None)
    if device is None:
        raise RuntimeError("未找到系统默认输出设备的回环输入")
    capture = SystemAudioCapture(device, module)
    manager, output = None, None
    found = []
    try:
        capture.start()
        manager = module.PyAudio()
        speaker = manager.get_default_wasapi_device(d_out=True)
        rate, channels = int(speaker["defaultSampleRate"]), min(2, int(speaker["maxOutputChannels"]))
        mono = (.06*np.sin(2*np.pi*440*np.arange(int(rate*1.5))/rate)).astype(np.float32)
        fade = int(rate*.02)
        mono[:fade] *= np.linspace(0,1,fade)
        mono[-fade:] *= np.linspace(1,0,fade)
        samples = np.repeat(mono[:, None], channels, axis=1)
        position = 0

        def play(data, frames, timing, status):
            nonlocal position
            block = samples[position:position+frames]
            position += len(block)
            return block.tobytes(), module.paComplete if position>=len(samples) else module.paContinue

        output = manager.open(format=module.paFloat32, channels=channels, rate=rate,
                              output=True, output_device_index=speaker["index"],
                              frames_per_buffer=rate//20, stream_callback=play)
        deadline = time.monotonic()+2.2
        while time.monotonic()<deadline:
            audio = capture.latest()
            if audio is not None:
                frequency = detect_frequency(audio, capture.rate)
                if frequency: found.append(frequency)
            time.sleep(.02)
        matched = [f for f in found if abs(f-440)<3]
        if len(matched)<2:
            raise RuntimeError("参考音回环检测未通过，请检查默认输出设备、音量和其他正在播放的声音")
        return {"passed": True, "expected_hz": 440, "detected_hz": round(float(np.median(matched)), 2),
                "sample_rate": capture.rate, "matched_windows": len(matched)}
    finally:
        try:
            if output:
                try: output.stop_stream()
                finally: output.close()
        finally:
            try:
                if manager: manager.terminate()
            finally:
                capture.stop()
