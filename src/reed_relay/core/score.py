from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import math
import os
from pathlib import Path
import tempfile
import uuid


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} 必须在 {low} 到 {high} 之间")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def pitch_name(pitch):
    return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[int(pitch) % 12] + str(int(pitch) // 12 - 1)


@dataclass(frozen=True)
class Note:
    start_ms: float
    duration_ms: float
    midi_pitch: int
    velocity: int = 90
    confidence: float = 1.0
    voice: str = "旋律"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    cents: float = 0.0

    def __post_init__(self):
        number(self.start_ms, "起始时间", 0, 86_400_000)
        number(self.duration_ms, "音符时长", .1, 86_400_000)
        number(self.midi_pitch, "MIDI 音高", 0, 127)
        number(self.velocity, "力度", 1, 127)
        number(self.confidence, "置信度", 0, 1)
        number(self.cents, "音分", -1200, 1200)
        if type(self.midi_pitch) is not int or type(self.velocity) is not int:
            raise ValueError("音高与力度须为整数")
        if not isinstance(self.id, str) or not self.id or not isinstance(self.voice, str):
            raise ValueError("音符标识与声部必须有效")

    @property
    def end_ms(self):
        return self.start_ms + self.duration_ms


@dataclass
class Score:
    title: str
    notes: list[Note] = field(default_factory=list)
    duration_ms: float = 0
    bpm: float = 120
    source_file: str = ""
    reference_hz: float = 440
    metadata: dict = field(default_factory=dict)
    schema_version: int = 1
    original_notes: list[Note] = field(default_factory=list)

    def validate(self):
        if self.schema_version != 1:
            raise ValueError(f"不支持的曲谱版本：{self.schema_version}")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("曲谱标题不能为空")
        number(self.duration_ms, "总时长", 0, 86_400_000)
        number(self.bpm, "速度", 10, 400)
        number(self.reference_hz, "参考频率", 400, 480)
        if not isinstance(self.metadata, dict) or not isinstance(self.source_file, str):
            raise ValueError("曲谱来源与元数据格式无效")
        if any(not isinstance(n, Note) for n in self.notes):
            raise ValueError("音符格式无效")
        if any(not isinstance(n, Note) for n in self.original_notes):
            raise ValueError("原始音符备份格式无效")
        if len({n.id for n in self.notes}) != len(self.notes):
            raise ValueError("存在重复音符标识")
        self.notes.sort(key=lambda n: (n.start_ms, n.midi_pitch))
        self.duration_ms = max(self.duration_ms, max((n.end_ms for n in self.notes), default=0))
        return self

    def save(self, path):
        self.validate()
        atomic_json(path, asdict(self))

    @classmethod
    def load(cls, path):
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict) or not isinstance(raw.get("notes"), list):
                raise ValueError("缺少 notes 音符列表")
            if len(raw["notes"]) > 500_000:
                raise ValueError("曲谱音符数量过多")
            raw["notes"] = [Note(**n) for n in raw["notes"]]
            raw["original_notes"] = [Note(**n) for n in raw.get("original_notes", [])]
            return cls(**raw).validate()
        except (TypeError, KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"曲谱格式错误：{e}") from e

    def export_midi(self, path):
        import mido
        self.validate()
        midi = mido.MidiFile(ticks_per_beat=1000)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        # One tick is one millisecond: event timing is independent of estimated BPM.
        track.append(mido.MetaMessage("set_tempo", tempo=1_000_000))
        events = []
        for n in self.notes:
            events.extend([(round(n.start_ms), 1, n), (round(n.end_ms), 0, n)])
        previous = 0
        for at, on, n in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(mido.Message("note_on" if on else "note_off", note=n.midi_pitch,
                                      velocity=n.velocity if on else 0, time=at - previous))
            previous = at
        track.append(mido.MetaMessage("end_of_track", time=max(0, round(self.duration_ms) - previous)))
        midi.save(str(path))

    @classmethod
    def from_midi(cls, path):
        import mido
        midi = mido.MidiFile(str(path))
        active, notes, elapsed = {}, [], 0.0
        for msg in midi:
            elapsed += msg.time * 1000
            if msg.type not in ("note_on", "note_off"):
                continue
            key = (msg.channel, msg.note)
            if msg.type == "note_on" and msg.velocity > 0:
                active.setdefault(key, []).append((elapsed, msg.velocity))
            elif active.get(key):
                start, velocity = active[key].pop(0)
                notes.append(Note(start, max(.1, elapsed - start), msg.note, velocity, voice=f"声部 {msg.channel + 1}"))
        for (channel, pitch), values in active.items():
            for start, velocity in values:
                notes.append(Note(start, max(100, elapsed - start), pitch, velocity, voice=f"声部 {channel + 1}"))
        return cls(Path(path).stem, notes, elapsed, source_file=str(path)).validate()

    def export_text(self, path):
        self.validate()
        degrees = ("1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7")
        lines = [self.title, "固定调简谱：1=C4；↑/↓表示高/低八度。时间与时长为秒，保留原谱节奏。",
                 "时间\t简谱\t音名\t时长\t声部"]
        for n in self.notes:
            octaves = n.midi_pitch // 12 - 5
            mark = "↑" * max(0, octaves) + "↓" * max(0, -octaves)
            lines.append(f"{n.start_ms / 1000:.3f}\t{degrees[n.midi_pitch % 12]}{mark}\t{pitch_name(n.midi_pitch)}\t{n.duration_ms / 1000:.3f}\t{n.voice}")
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def extract_melody(notes: list[Note]) -> list[Note]:
    """An explicit, editable monophonic reduction; callers retain original notes."""
    if not notes:
        return []
    starts, ends = {}, {}
    for n in notes:
        starts.setdefault(round(n.start_ms, 3), []).append(n)
        ends.setdefault(round(n.end_ms, 3), []).append(n)
    times = sorted(set(starts) | set(ends))
    active, result, previous_pitch = {}, [], None
    for i, time in enumerate(times[:-1]):
        for n in ends.get(time, []):
            active.pop(n.id, None)
        for n in starts.get(time, []):
            active[n.id] = n
        if not active:
            continue
        chosen = max(active.values(), key=lambda n: n.confidence + n.midi_pitch * .006 -
                     (abs(n.midi_pitch - previous_pitch) * .008 if previous_pitch is not None else 0))
        until = times[i + 1]
        if until - time < .1:
            continue
        if result and result[-1].id.startswith(chosen.id + "_") and abs(result[-1].end_ms - time) < .01:
            result[-1] = replace(result[-1], duration_ms=until - result[-1].start_ms)
        else:
            result.append(replace(chosen, start_ms=time, duration_ms=until - time, id=f"{chosen.id}_{i}"))
        previous_pitch = chosen.midi_pitch
    return result
