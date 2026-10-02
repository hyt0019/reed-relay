"""Dependency-light harmonica synthesis shared by both standalone applications."""
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
import threading
import wave
import numpy as np
from .tuning import frequency_for


class RenderCancelled(Exception):
    pass


@lru_cache(maxsize=1)
def sound_bank():
    data = json.loads((Path(__file__).parents[1] / "assets" / "harmonica.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or len(data.get("models", [])) != 5:
        raise ValueError("口琴音色库无效，请重新安装程序")
    return data["models"]


def choose_model(pitch):
    models = {v["id"]: v for v in sound_bank()}
    if pitch < 60:
        return models["lower"]
    if pitch >= 72:
        return models["upper"]
    if pitch % 12 in {1, 3, 6, 8, 10}:
        return models["sharp"]
    return models["normal_c" if pitch == 60 else "normal_d"]


def _phase_time(t, knots, ratios):
    """Analytically integrate the piecewise-linear frequency ratio: no block seams."""
    widths = np.diff(knots)
    cumulative = np.r_[0., np.cumsum((ratios[:-1]+ratios[1:])*.5*widths)]
    indices = np.clip(np.searchsorted(knots, t, side="right")-1, 0, len(knots)-2)
    dt = np.clip(t-knots[indices], 0, widths[indices])
    integral = cumulative[indices]+ratios[indices]*dt+.5*(ratios[indices+1]-ratios[indices])/widths[indices]*dt*dt
    return np.where(t >= knots[-1], cumulative[-1]+(t-knots[-1])*ratios[-1], integral)


def note_audio(pitch, relative, duration, reference_hz=440, velocity=100, mode="clean", rate=44100, cents=0):
    model = choose_model(pitch)
    times = np.asarray(model["times"])
    harmonics = np.asarray(model["harmonics"])
    # Clean audition retains a short onset and then the measured stable timbre.
    age = np.maximum(relative, 0) if mode == "game" else np.minimum(np.maximum(relative, 0)*3, .8)
    frequency = frequency_for(pitch + (0 if mode == "game" else cents/100), reference_hz)
    phase = 2*np.pi*frequency*(_phase_time(np.maximum(relative, 0), times, 2**(np.asarray(model["cents"])/1200)) if mode == "game" else relative)
    output = np.zeros_like(relative)
    for index in range(harmonics.shape[1]):
        harmonic = index+1
        if frequency*harmonic*1.05 >= rate*.48:
            break
        amplitude = np.interp(age, times, harmonics[:, index])
        # Deterministic phases keep harmonics from all peaking simultaneously.
        output += amplitude*np.sin(harmonic*phase + index*index*2.39996323)
    envelope = np.minimum(np.clip(relative/.003, 0, 1), np.clip((duration-relative)/.008, 0, 1))
    return output*envelope*(velocity/100)*2.8


def synthesize_harmonica(score, path, cancel=None, speed=1., mode="clean", progress=lambda _: None):
    """Render absolute score timing at the chosen speed without shifting pitch.

    Audio is written in blocks to a temporary file then atomically replaced.
    The score is never edited, and long files use bounded audio memory.
    """
    score.validate()
    if not .25 <= speed <= 2 or mode not in {"clean", "game"}:
        raise ValueError("试听速度或音色模式无效")
    cancel = cancel or threading.Event()
    path = Path(path)
    temporary = path.with_name(path.name+".part")
    rate, chunk = 44100, 4096
    notes = sorted((replace(n, start_ms=n.start_ms/speed, duration_ms=n.duration_ms/speed) for n in score.notes), key=lambda n:n.start_ms)
    length = round(score.duration_ms/1000/speed*rate)
    active, index = [], 0
    try:
        with wave.open(str(temporary), "wb") as writer:
            writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(rate)
            for start in range(0, length, chunk):
                if cancel.is_set():
                    raise RenderCancelled("试听生成已取消")
                stop = min(length, start+chunk)
                while index < len(notes) and notes[index].start_ms/1000 < stop/rate:
                    active.append(notes[index]); index += 1
                active = [n for n in active if n.end_ms/1000 > start/rate]
                t = np.arange(start, stop)/rate
                block = np.zeros(stop-start)
                for n in active:
                    block += note_audio(n.midi_pitch, t-n.start_ms/1000, n.duration_ms/1000,
                                        score.reference_hz, n.velocity, mode, rate, n.cents)
                # Smooth output limiting handles dense polyphonic score candidates.
                writer.writeframes((np.tanh(block)*32767).astype("<i2").tobytes())
                progress(stop/max(1, length))
        if cancel.is_set():
            raise RenderCancelled("试听生成已取消")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
