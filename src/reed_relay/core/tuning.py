from __future__ import annotations

import math
import numpy as np
from .score import pitch_name


def frequency_for(pitch, reference_hz=440):
    return reference_hz * 2 ** ((pitch - 69) / 12)


def describe_frequency(hz, reference_hz=440):
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError("频率须为正数")
    exact = 69 + 12 * math.log2(hz / reference_hz)
    pitch = round(exact)
    return {"frequency": round(hz, 2), "pitch": pitch, "name": pitch_name(pitch), "cents": round((exact - pitch) * 100, 1)}


def detect_frequency(audio, sample_rate, fmin=55, fmax=1800):
    """Normalized autocorrelation; rejects silence and weak periodicity."""
    a = np.asarray(audio, dtype=np.float64)
    if a.ndim == 2:
        a = a.mean(axis=1)
    a = a[-min(len(a), int(sample_rate * .25)):]
    if len(a) < sample_rate / fmin * 3:
        return None
    a = a - np.mean(a)
    if np.sqrt(np.mean(a * a)) < .003:
        return None
    fft_size = 1 << (2 * len(a) - 1).bit_length()
    autocorr = np.fft.irfft(abs(np.fft.rfft(a, fft_size)) ** 2, fft_size)[:len(a)]
    energy = np.concatenate(([0.], np.cumsum(a * a)))
    lag = np.arange(len(a))
    denom = energy[len(a) - lag] + energy[-1] - energy[lag]
    normalized = 2 * autocorr / np.maximum(denom, 1e-12)
    lo, hi = max(2, int(sample_rate / fmax)), min(len(a) - 2, int(sample_rate / fmin))
    peaks = [i for i in range(lo, hi) if normalized[i] >= normalized[i-1] and normalized[i] > normalized[i+1]]
    if not peaks:
        return None
    best = max(normalized[i] for i in peaks)
    if best < .75:
        return None
    chosen = next(i for i in peaks if normalized[i] >= max(.75, best * .92))
    left, mid, right = normalized[chosen-1:chosen+2]
    denominator = left - 2 * mid + right
    delta = .5 * (left - right) / denominator if abs(denominator) > 1e-12 else 0
    return float(sample_rate / (chosen + delta))


def tone(pitch, reference_hz=440, seconds=.8, sample_rate=44100):
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    a = np.sin(2 * np.pi * frequency_for(pitch, reference_hz) * t)
    fade = min(len(a) // 2, int(sample_rate * .02))
    if fade:
        a[:fade] *= np.linspace(0, 1, fade)
        a[-fade:] *= np.linspace(1, 0, fade)
    return (a * .18).astype(np.float32)
