"""A deterministic guided calibration state machine, independent of Windows/Qt."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .profile import Profile
from .score import pitch_name


def key_label(key):
    return {"MOUSE_LEFT": "鼠标左键", "MOUSE_MIDDLE": "鼠标中键", "MOUSE_RIGHT": "鼠标右键", ",": "逗号"}.get(key, key)


@dataclass(frozen=True)
class CalibrationStep:
    base: int
    modifiers: tuple[int, ...] = ()

    @property
    def optional(self): return len(self.modifiers) > 1


class GuidedCalibration:
    def __init__(self, profile: Profile, now: float):
        self.original = Profile.from_dict(profile.to_dict())
        self.controls = set(profile.keys + [m.key for m in profile.modifiers])
        self.steps = [CalibrationStep(i) for i in range(8)]
        for modifiers in [(0,), (1,), (2,)] + [tuple(c) for c in profile.combinations if len(c)>1]:
            self.steps.extend(CalibrationStep(i, modifiers) for i in (0, 1))
        self.index, self.next_index = 0, 0
        self.phase, self.paused = "prepare", False
        self.deadline = now + 3
        self.values = {}
        self.samples = []
        self.held_since, self.released_since = None, None
        self.hint = "请切回游戏，进入乐器演奏界面"
        self.last_note = ""
        self.result = None

    @property
    def active(self): return self.phase not in ("done", "cancelled", "failed")

    @property
    def step(self): return self.steps[min(self.index, len(self.steps)-1)]

    @property
    def expected(self):
        return {self.original.keys[self.step.base]} | {self.original.modifiers[i].key for i in self.step.modifiers}

    def reset_hold(self):
        self.held_since = None
        self.samples.clear()

    def tick(self, now, held, foreground, sample=None):
        if not self.active: return
        held = set(held) & self.controls
        if not foreground:
            self.reset_hold()
            self.released_since = None
            if self.phase == "listen": self.phase = "release"
            self.hint = "请切回选定游戏；松开按键后继续"
            return
        if self.paused:
            self.hint = "已暂停；按启停热键继续"
            return
        if self.phase == "prepare":
            if now < self.deadline:
                self.hint = f"准备调音 · {math.ceil(self.deadline-now)} 秒，请松开演奏键"
                return
            self.phase = "release"
        if self.phase == "release":
            if held:
                self.released_since = None
                self.hint = "已记录，请松开所有演奏键" if self.last_note else "请先松开所有音符键和修饰键"
                return
            if self.released_since is None: self.released_since = now
            if now - self.released_since < .4 or now < self.deadline: return
            self.index = self.next_index
            if self.index >= len(self.steps):
                self.result = self.build_result()
                self.phase = "done"
                self.hint = "所有测音步骤完成，正在保存场景"
                return
            self.phase = "listen"
            self.reset_hold()
        if held != self.expected:
            self.reset_hold()
            self.hint = "请只按提示中的按键，并保持约 1 秒" if held else "按住提示按键；稳定后自动记录"
            return
        if self.held_since is None: self.held_since = now
        if now - self.held_since < .4:
            self.hint = "保持按住，等待声音稳定"
            return
        if sample is None: return  # Only fresh audio frames count toward stability.
        if not sample.get("frequency"):
            self.samples.clear()
            self.hint = "未检测到稳定单音，请检查音量并关闭背景音乐"
            return
        pitch, cents = sample["pitch"], sample["cents"]
        if not 0 <= pitch <= 127 or abs(cents)>30:
            self.samples.clear()
            self.hint = "音高偏差较大，请检查背景声音或 A4 参考频率"
            return
        if self.samples and (now-self.samples[-1][2]>.6 or pitch != self.samples[-1][0] or abs(cents-self.samples[-1][1])>20):
            self.samples.clear()
        self.samples.append((pitch, cents, now))
        self.samples = self.samples[-3:]
        self.hint = f"正在确认 {pitch_name(pitch)} · {len(self.samples)}/3"
        if len(self.samples)<3 or self.samples[-1][2]-self.samples[0][2]<.4: return
        problem = self.validate_pitch(pitch)
        if problem:
            self.samples.clear()
            self.hint = problem
            return
        self.values[self.index] = pitch
        self.last_note = f"{self.instruction()} → {pitch_name(pitch)} / MIDI {pitch}"
        self.next_index = self.index+1
        self.phase, self.deadline, self.released_since = "release", now+.7, None
        self.reset_hold()
        self.hint = "完成，请松开按键"

    def validate_pitch(self, pitch):
        step = self.step
        if not step.modifiers: return ""
        offset = pitch - self.values[step.base]
        if len(step.modifiers)==1:
            if not -48 <= offset <= 48: return "修饰音程超出范围，请松开后重新测音"
            if step.base == 1:
                first = next(i for i,s in enumerate(self.steps) if s.modifiers==step.modifiers and s.base==0)
                if offset != self.values[first]-self.values[0]:
                    return "两次修饰音程不一致；请重测，或用重测热键返回上一步"
        else:
            expected = sum(self.modifier_shift(i) for i in step.modifiers)
            if offset != expected:
                return "该组合与单键音程不符；请重试，或按跳过热键禁用此组合"
        return ""

    def modifier_shift(self, modifier):
        first = next(i for i,s in enumerate(self.steps) if s.modifiers==(modifier,) and s.base==0)
        return self.values[first]-self.values[0]

    def instruction(self):
        parts = [key_label(self.original.modifiers[i].key) for i in self.step.modifiers]
        return " + ".join(parts+[key_label(self.original.keys[self.step.base])])

    def toggle_pause(self):
        if not self.active: return
        self.paused = not self.paused
        self.reset_hold()
        self.released_since = None
        if self.phase == "listen": self.phase = "release"
        self.hint = "已暂停；按启停热键继续" if self.paused else "已继续，请松开按键后按提示操作"

    def rewind(self):
        if not self.active: return
        target = self.index if self.phase == "release" and self.index in self.values else max(0, self.index-1)
        step = self.steps[target]
        if step.optional:
            target = next(i for i,s in enumerate(self.steps) if s.modifiers==step.modifiers)
        self.values = {i:v for i,v in self.values.items() if i<target}
        self.index = self.next_index = target
        self.phase, self.paused, self.last_note = "release", False, ""
        self.released_since = None
        self.reset_hold()
        self.hint = "准备重测，请松开按键"

    def skip(self, now):
        if not self.active: return
        if not self.step.optional:
            self.hint = "基础音和单个修饰是必测项，不能跳过"
            return
        combo = self.step.modifiers
        indices = [i for i,s in enumerate(self.steps) if s.modifiers==combo]
        for i in indices: self.values[i] = None
        self.next_index = max(indices)+1
        self.phase, self.deadline, self.released_since = "release", now+.7, None
        self.last_note = "已禁用此组合"
        self.reset_hold()
        self.hint = "已跳过此组合，请松开按键"

    def build_result(self):
        result = Profile.from_dict(self.original.to_dict())
        result.pitches = [self.values[i] for i in range(8)]
        for i, modifier in enumerate(result.modifiers): modifier.semitones = self.modifier_shift(i)
        result.combinations = [list(c) for c in self.original.combinations if len(c)<=1 or
                               all(self.values.get(i) is not None for i,s in enumerate(self.steps) if s.modifiers==tuple(c))]
        result.calibrated = True
        return result.validate()

    def cancel(self, message="调音已取消，原场景保持不变"):
        self.phase, self.hint = "cancelled", message
        self.reset_hold()

    def fail(self, message):
        self.phase, self.hint = "failed", message
        self.reset_hold()

    def snapshot(self):
        title = {"prepare":"准备调音", "release":"松开按键", "listen":"请按住", "done":"调音结束", "cancelled":"调音已取消", "failed":"调音未完成"}[self.phase]
        if self.paused: title = "调音已暂停"
        return {"active":self.active, "phase":self.phase, "title":title,
                "instruction":self.instruction() if self.active else "",
                "hint":self.hint, "last_note":self.last_note,
                "step":min(self.index+1,len(self.steps)), "total":len(self.steps),
                "progress":min(1.,len(self.values)/len(self.steps)), "stability":len(self.samples)/3,
                "optional":self.step.optional, "paused":self.paused}
