from __future__ import annotations

import math
from pathlib import Path
import subprocess
import threading
import wave
import numpy as np
from reed_relay.core.tuning import frequency_for


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set(): raise Cancelled("处理已取消，已完成的曲谱仍保留")


def decode(path, cancel=None):
    cancel = cancel or threading.Event()
    check_cancel(cancel)
    import soundfile as sf
    from scipy.signal import resample_poly
    try:
        audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if rate != 22050:
            divisor = math.gcd(rate, 22050)
            audio = resample_poly(audio, 22050 // divisor, rate // divisor).astype(np.float32)
    except (RuntimeError, ValueError, sf.LibsndfileError):
        import imageio_ffmpeg
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "22050", "-f", "f32le", "pipe:1"]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while True:
                try:
                    output, errors = proc.communicate(timeout=.15)
                    break
                except subprocess.TimeoutExpired:
                    check_cancel(cancel)
            if proc.returncode:
                raise ValueError("音频解码失败：" + errors.decode("utf-8", errors="replace")[-500:])
            audio = np.frombuffer(output, dtype="<f4").copy()
        finally:
            if proc.poll() is None:
                proc.kill(); proc.communicate()
    check_cancel(cancel)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError("音频为空或包含无效样本")
    return audio, 22050


def waveform_peaks(audio, count=420):
    if not len(audio): return []
    stride = max(1, math.ceil(len(audio) / count))
    peaks = [float(np.max(np.abs(audio[i:i+stride]))) for i in range(0, len(audio), stride)]
    maximum = max(peaks, default=1) or 1
    return [v / maximum for v in peaks]


def synthesize(score, path, cancel=None):
    """Write a complete preview in bounded blocks, without a long audio allocation."""
    cancel = cancel or threading.Event()
    rate, chunk = 22050, 4096
    notes = sorted(score.notes, key=lambda n: n.start_ms)
    active, index = [], 0
    length = round(score.duration_ms / 1000 * rate)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(rate)
        for start in range(0, length, chunk):
            check_cancel(cancel)
            stop = min(length, start+chunk)
            t = np.arange(start, stop) / rate
            while index < len(notes) and notes[index].start_ms / 1000 < stop / rate:
                active.append(notes[index]); index += 1
            active = [n for n in active if n.end_ms / 1000 > start / rate]
            data = np.zeros(stop-start, dtype=np.float64)
            for n in active:
                relative = t - n.start_ms / 1000
                duration = n.duration_ms / 1000
                envelope = np.minimum(np.clip(relative/.01, 0, 1), np.clip((duration-relative)/.02, 0, 1))
                freq = frequency_for(n.midi_pitch+n.cents/100, score.reference_hz)
                data += np.sin(2*np.pi*freq*relative) * envelope * n.velocity/127
            data = np.tanh(data*.25)
            writer.writeframes((data * 32767).astype("<i2").tobytes())

