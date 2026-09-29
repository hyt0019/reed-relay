from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from .score import Note, Score, atomic_json, number, pitch_name


KEYS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | {f"F{i}" for i in range(1, 25)} | {
    ",", ".", ";", "'", "[", "]", "\\", "/", "-", "=", "`", "SPACE", "TAB", "ENTER", "ESC", "PAUSE",
    "HOME", "END", "INSERT", "DELETE", "PAGEUP", "PAGEDOWN", "UP", "DOWN", "LEFT", "RIGHT",
    "MOUSE_LEFT", "MOUSE_MIDDLE", "MOUSE_RIGHT", "SHIFT", "CTRL", "ALT"}


def normalize_key(key):
    key = str(key).strip().upper()
    aliases = {"，": ",", "鼠标左键": "MOUSE_LEFT", "鼠标中键": "MOUSE_MIDDLE", "鼠标右键": "MOUSE_RIGHT", "ESCAPE": "ESC"}
    key = aliases.get(key, key)
    if key not in KEYS:
        raise ValueError(f"不支持的按键：{key}")
    return key


def validate_hotkeys(hotkeys):
    required = {"toggle", "previous", "next", "emergency"}
    if set(hotkeys) != required:
        raise ValueError("必须设置启停、上一首、下一首和紧急停止四个热键")
    normalized = {}
    for name, value in hotkeys.items():
        parts = str(value).upper().replace(" ", "").split("+")
        key = normalize_key(parts[-1])
        if key == "F12":
            raise ValueError("F12 是 Windows 调试器保留热键，请改用 F10 等按键")
        mods = set(parts[:-1])
        if not mods <= {"CTRL", "ALT", "SHIFT", "WIN"} or key.startswith("MOUSE_") or key in {"CTRL", "ALT", "SHIFT"}:
            raise ValueError(f"全局热键无效：{value}")
        normalized[name] = "+".join(sorted(mods) + [key])
    if len(set(normalized.values())) != 4:
        raise ValueError("全局热键不能重复")
    return normalized


@dataclass
class Modifier:
    label: str
    key: str
    semitones: int


@dataclass
class Profile:
    name: str = "默认口琴（待校准）"
    keys: list[str] = field(default_factory=lambda: ["Z", "X", "C", "V", "B", "N", "M", ","])
    pitches: list[int] = field(default_factory=lambda: [60, 62, 64, 65, 67, 69, 71, 72])
    modifiers: list[Modifier] = field(default_factory=lambda: [Modifier("降调", "MOUSE_LEFT", -12), Modifier("半音", "MOUSE_MIDDLE", 1), Modifier("升调", "MOUSE_RIGHT", 12)])
    combinations: list[list[int]] = field(default_factory=lambda: [[], [0], [1], [2], [0, 1], [1, 2]])
    reference_hz: float = 440
    calibrated: bool = False
    hotkeys: dict = field(default_factory=lambda: {"toggle": "F8", "previous": "F6", "next": "F7", "emergency": "F10"})
    schema_version: int = 1

    def validate(self):
        if self.schema_version != 1 or not self.name.strip():
            raise ValueError("场景名称或版本无效")
        if len(self.keys) != 8 or len(self.pitches) != 8 or len(self.modifiers) != 3:
            raise ValueError("当前口琴配置需要 8 个音符键与 3 个修饰键")
        self.keys = [normalize_key(k) for k in self.keys]
        for p in self.pitches:
            number(p, "基础音高", 0, 127)
            if type(p) is not int:
                raise ValueError("基础音高须为 MIDI 整数")
        for mod in self.modifiers:
            mod.key = normalize_key(mod.key)
            number(mod.semitones, "修饰音程", -48, 48)
            if type(mod.semitones) is not int:
                raise ValueError("音程须为整数半音")
        controls = self.keys + [m.key for m in self.modifiers]
        if len(set(controls)) != len(controls):
            raise ValueError("音符键与修饰键不能重复")
        for combo in self.combinations:
            if len(set(combo)) != len(combo) or any(type(i) is not int or i not in range(3) for i in combo):
                raise ValueError("修饰组合无效")
        if [] not in self.combinations:
            raise ValueError("必须保留不使用修饰的基础音")
        number(self.reference_hz, "A4 基准", 400, 480)
        self.hotkeys = validate_hotkeys(self.hotkeys)
        if any(v.split("+")[-1] in controls for v in self.hotkeys.values()):
            raise ValueError("热键与演奏键冲突，请使用其他热键")
        if type(self.calibrated) is not bool:
            raise ValueError("校准状态无效")
        return self

    def to_dict(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["modifiers"] = [Modifier(**v) for v in data.get("modifiers", [])]
        try:
            return cls(**data).validate()
        except (TypeError, KeyError) as e:
            raise ValueError(f"场景配置格式错误：{e}") from e

    def save(self, path):
        atomic_json(path, self.to_dict())

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def mapping(self):
        self.validate()
        result = {}
        for combo in sorted(self.combinations, key=len):
            shift = sum(self.modifiers[i].semitones for i in combo)
            for key, pitch in zip(self.keys, self.pitches):
                mapped = pitch + shift
                if 0 <= mapped <= 127:
                    result.setdefault(mapped, (key, tuple(self.modifiers[i].key for i in combo)))
        return result


@dataclass(frozen=True)
class Event:
    at_ms: float
    down: bool
    key: str
    note_id: str = ""
    pitch: int = -1
    priority: int = 0


@dataclass
class Plan:
    events: list[Event]
    issues: list[dict]
    duration_ms: float
    note_count: int

    @property
    def playable(self):
        return self.note_count > 0 and not any(i["blocking"] for i in self.issues)


def make_plan(score: Score, profile: Profile, transpose=0, skip_unmapped=False) -> Plan:
    score.validate()
    number(transpose, "演奏移调", -48, 48)
    if type(transpose) is not int:
        raise ValueError("移调须为整数半音")
    mapping, events, issues, playable = profile.mapping(), [], [], []
    for n in score.notes:
        pitch = n.midi_pitch + transpose
        if pitch not in mapping:
            issues.append({"id": n.id, "message": f"{pitch_name(pitch)} 超出当前场景音域", "blocking": not skip_unmapped, "kind": "range"})
            continue
        if abs(n.cents) > 20:
            issues.append({"id": n.id, "message": "离散按键无法精确还原滑音/音分偏移", "blocking": False, "kind": "cents"})
        if n.confidence < .5:
            issues.append({"id": n.id, "message": "识别置信度较低，建议试听", "blocking": False, "kind": "confidence"})
        playable.append(n)
        key, mods = mapping[pitch]
        events.extend([Event(n.start_ms, True, key, n.id, pitch, 3), Event(n.end_ms, False, key, n.id, pitch, 0)])
        for mod in mods:
            events.extend([Event(n.start_ms, True, mod, priority=2), Event(n.end_ms, False, mod, priority=1)])
    end = -1
    for n in playable:
        if n.start_ms < end - .01:
            issues.append({"id": n.id, "message": "存在重叠音，请选择主旋律或编辑时长", "blocking": True, "kind": "overlap"})
        end = max(end, n.end_ms)
    if abs(score.reference_hz - profile.reference_hz) > .5:
        issues.append({"id": "", "message": "曲谱与场景的 A4 参考频率不同，请校准后确认音高", "blocking": False, "kind": "tuning"})
    return Plan(sorted(events, key=lambda e: (e.at_ms, e.priority)), issues, score.duration_ms, len(playable))
