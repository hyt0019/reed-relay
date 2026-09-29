from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import queue
import sys
import threading
import wave

import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl
from PySide6.QtWidgets import QFileDialog
from reed_relay.core.score import Score, Note, atomic_json, pitch_name, extract_melody
from reed_relay.core.profile import Profile, make_plan
from reed_relay.core.tuning import tone, detect_frequency, describe_frequency
from reed_relay.player.engine import PlayerEngine, PreviewOutput
from reed_relay.player.windows import Hotkeys, WindowsOutput, windows, focus_guard


class Backend(QObject):
    changed = Signal()
    scoreChanged = Signal()
    profileChanged = Signal()
    playlistChanged = Signal()
    issuesChanged = Signal()
    windowsChanged = Signal()
    report = Signal(str, object)
    hotkeyReceived = Signal(str)

    def __init__(self, mode="player", no_hotkeys=False):
        super().__init__()
        self.mode = mode
        self.data_dir = Path(os.environ.get("REED_RELAY_DATA_DIR", str(Path(os.environ.get("APPDATA", str(Path.home()))) / "ReedRelay")))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._profile = Profile()
        self._score = Score("还没有添加曲谱")
        self._playlist, self._windows, self._issues, self._undo, self._redo = [], [], [], [], []
        self._selected = -1
        self._message, self._state, self._hotkey_status = "添加曲谱后即可预演", "待机", ""
        self._progress, self._active_pitch, self._active_key = 0., -1, ""
        self._preview, self._speed, self._delay, self._transpose = True, 1., 3., 0
        self._melody, self._skip, self._target = False, False, -1
        self._tune, self._stream, self._mic_queue = {}, None, queue.Queue(maxsize=2)
        self._busy, self._conversion_progress, self._audio_path, self._waveform = False, 0., "", []
        self._conversion_cancel = threading.Event()
        self._no_hotkeys = no_hotkeys
        self.engine = PlayerEngine(lambda kind, value: self.report.emit(kind, value))
        self.report.connect(self._handle_report)
        self.hotkeyReceived.connect(self._on_hotkey)
        self.hotkeys = Hotkeys(self.hotkeyReceived.emit, lambda msg: self.report.emit("hotkeys", msg))
        try:
            if (self.data_dir / "profile.json").exists():
                self._profile = Profile.load(self.data_dir / "profile.json")
            if (self.data_dir / "playlist.json").exists():
                items = json.loads((self.data_dir / "playlist.json").read_text(encoding="utf-8"))
                for path in items:
                    if Path(path).is_file():
                        self._add_score(path)
        except Exception as e:
            self._message = f"读取本地配置失败：{e}"
        self._mic_timer = QTimer(self)
        self._mic_timer.setInterval(120)
        self._mic_timer.timeout.connect(self._read_mic)
        if mode == "player" and not no_hotkeys:
            self.hotkeys.start(self._profile.hotkeys)
        self.refreshWindows()

    @Property(str, constant=True)
    def appMode(self): return self.mode
    @Property(str, notify=changed)
    def message(self): return self._message
    @Property(str, notify=changed)
    def state(self): return self._state
    @Property(str, notify=scoreChanged)
    def title(self): return self._score.title
    @Property(str, notify=changed)
    def hotkeyStatus(self): return self._hotkey_status
    @Property("QVariantMap", notify=profileChanged)
    def profile(self): return self._profile.to_dict()
    @Property("QVariantList", notify=playlistChanged)
    def playlist(self): return self._playlist
    @Property("QVariantList", notify=windowsChanged)
    def windowList(self): return self._windows
    @Property("QVariantList", notify=issuesChanged)
    def issues(self): return self._issues
    @Property("QVariantList", notify=scoreChanged)
    def notes(self):
        return [asdict(n) | {"name": pitch_name(n.midi_pitch)} for n in self._score.notes]
    @Property(int, notify=changed)
    def selected(self): return self._selected
    @Property(int, notify=changed)
    def activePitch(self): return self._active_pitch
    @Property(str, notify=changed)
    def activeKey(self): return self._active_key
    @Property(float, notify=scoreChanged)
    def duration(self): return self._score.duration_ms
    @Property(float, notify=changed)
    def progress(self): return self._progress
    @Property(bool, notify=changed)
    def running(self): return self._state in ("演奏中", "倒计时")
    @Property("QVariantMap", notify=changed)
    def tuning(self): return self._tune
    @Property(bool, notify=changed)
    def listening(self): return self._stream is not None
    @Property(bool, notify=changed)
    def busy(self): return self._busy
    @Property(float, notify=changed)
    def conversionProgress(self): return self._conversion_progress
    @Property(str, notify=changed)
    def audioPath(self): return self._audio_path
    @Property("QVariantList", notify=changed)
    def waveform(self): return self._waveform
    @Property(bool, notify=changed)
    def canUndo(self): return bool(self._undo)
    @Property(bool, notify=changed)
    def canRedo(self): return bool(self._redo)

    def _error(self, e):
        self._message = str(e)
        self.changed.emit()

    def _prepared_score(self):
        return replace(self._score, notes=extract_melody(self._score.notes)) if self._melody else self._score

    def _check(self):
        try:
            self._issues = make_plan(self._prepared_score(), self._profile, self._transpose, self._skip).issues
        except Exception as e:
            self._issues = [{"message": str(e), "blocking": True}]
        self.issuesChanged.emit()

    @Slot(str, object)
    def _handle_report(self, kind, value):
        if kind == "state": self._state = value
        elif kind == "progress": self._progress = value
        elif kind == "note":
            self._active_pitch = value["pitch"] if value["down"] else -1
            self._active_key = value["key"] if value["down"] else ""
        elif kind == "countdown": self._message = f"{value:.1f} 秒后开始，请切换至游戏窗口"
        elif kind == "finished":
            self._state, self._message, self._active_pitch, self._active_key = "待机", value, -1, ""
        elif kind == "hotkeys": self._hotkey_status = value
        elif kind == "error": self._message = value
        self.changed.emit()

    @Slot(str)
    def _on_hotkey(self, action):
        if action in ("toggle", "emergency"):
            self.stop() if action == "emergency" else self.toggle()
        elif action == "previous": self.stepSong(-1)
        elif action == "next": self.stepSong(1)

    def _add_score(self, path):
        score = Score.from_midi(path) if str(path).lower().endswith((".mid", ".midi")) else Score.load(path)
        normalized = str(Path(path).resolve())
        if not any(item["path"] == normalized for item in self._playlist):
            self._playlist.append({"path": normalized, "title": score.title, "duration": score.duration_ms})
        self._score, self._selected = score, next(i for i, item in enumerate(self._playlist) if item["path"] == normalized)
        self._progress = 0
        self._check()
        self.scoreChanged.emit()
        self.playlistChanged.emit()

    @Slot()
    def openScores(self):
        paths, _ = QFileDialog.getOpenFileNames(None, "添加曲谱", "", "曲谱 (*.reedscore.json *.json *.mid *.midi)")
        self.stop()
        for path in paths:
            try: self._add_score(path)
            except Exception as e: self._error(e)
        self._save_playlist()
        self.changed.emit()

    @Slot()
    def loadDemo(self):
        self.stop()
        self._score = Score("晨风 · 练习曲", [Note(i*400,320,p) for i,p in enumerate([60,64,67,72,71,69,67,64,62,65,69,72,67,64,62,60])], 6600)
        path = self.data_dir / "晨风.reedscore.json"
        self._score.save(path)
        self._add_score(path)
        self._save_playlist()
        self._message = "已载入原创练习曲；预演只显示按键，不发送游戏输入"
        self.changed.emit()

    def _save_playlist(self):
        atomic_json(self.data_dir / "playlist.json", [v["path"] for v in self._playlist])

    @Slot(int)
    def selectSong(self, index):
        if not 0 <= index < len(self._playlist): return
        self.stop()
        try: self._add_score(self._playlist[index]["path"])
        except Exception as e: self._error(e)
        self.changed.emit()

    @Slot(int)
    def stepSong(self, delta):
        if self._playlist:
            self.selectSong((self._selected + delta) % len(self._playlist))

    @Slot(int)
    def removeSong(self, index):
        self.stop()
        if 0 <= index < len(self._playlist):
            self._playlist.pop(index)
            self._selected = -1
            self._score = Score("还没有添加曲谱")
            if self._playlist: self.selectSong(min(index, len(self._playlist)-1))
            self._save_playlist()
            self._check()
            self.scoreChanged.emit()
            self.playlistChanged.emit()
            self.changed.emit()

    @Slot(bool, float, float, int, bool, bool, int)
    def configurePlayer(self, preview, speed, delay, transpose, melody, skip, target):
        self._preview, self._speed, self._delay, self._transpose = preview, speed, delay, transpose
        self._melody, self._skip, self._target = melody, skip, target
        self._check()
        self.changed.emit()

    @Slot()
    def toggle(self):
        if self.engine.running:
            self.stop()
            return
        try:
            if not self._preview and not self._profile.calibrated:
                raise ValueError("请在调音页核对实际音高并确认校准，再启用游戏输入")
            if not self._preview and not 0 <= self._target < len(self._windows):
                raise ValueError("请选择目标游戏窗口")
            plan = make_plan(self._prepared_score(), self._profile, self._transpose, self._skip)
            self._issues = plan.issues
            self.issuesChanged.emit()
            self._progress = 0
            self.engine.start(plan, PreviewOutput() if self._preview else WindowsOutput(), self._speed,
                              0 if self._preview else self._delay,
                              (lambda: True) if self._preview else focus_guard(self._windows[self._target]))
            self._message = "预演中：未发送按键" if self._preview else "准备向选定游戏窗口发送按键"
        except Exception as e: self._message = str(e)
        self.changed.emit()

    @Slot()
    def stop(self):
        self.engine.stop()

    @Slot()
    def refreshWindows(self):
        try: self._windows = windows()
        except Exception as e: self._message = str(e)
        self.windowsChanged.emit()
        self.changed.emit()

    @Slot(str)
    def saveProfile(self, raw):
        try:
            self.stop()
            new_profile = Profile.from_dict(json.loads(raw))
            new_profile.save(self.data_dir / "profile.json")
            self._profile = new_profile
            self.profileChanged.emit()
            if self.mode == "player" and not self._no_hotkeys:
                self.hotkeys.start(self._profile.hotkeys)
            self._check()
            self._message = "场景已保存，调音与自定义键位已应用"
        except Exception as e: self._message = str(e)
        self.changed.emit()

    @Slot()
    def exportProfile(self):
        path, _ = QFileDialog.getSaveFileName(None, "导出场景", self._profile.name + ".profile.json", "场景 (*.json)")
        if path:
            try: self._profile.save(path); self._error("场景已导出")
            except Exception as e: self._error(e)

    @Slot()
    def importProfile(self):
        path, _ = QFileDialog.getOpenFileName(None, "导入场景", "", "场景 (*.json)")
        if path:
            try: self.saveProfile(json.dumps(Profile.load(path).to_dict()))
            except Exception as e: self._error(e)

    @Slot(int, float)
    def playTone(self, pitch, reference):
        try:
            import sounddevice as sd
            sd.play(tone(pitch, reference), 44100)
        except Exception as e: self._error(f"参考音播放失败：{e}")

    @Slot()
    def toggleMic(self):
        try:
            if self._stream:
                self._mic_timer.stop()
                self._stream.stop(); self._stream.close(); self._stream = None
            else:
                import sounddevice as sd
                def callback(data, frames, timing, status):
                    try: self._mic_queue.put_nowait(data.copy())
                    except queue.Full: pass
                self._stream = sd.InputStream(samplerate=44100, channels=1, blocksize=11025, callback=callback)
                self._stream.start()
                self._mic_timer.start()
            self.changed.emit()
        except Exception as e:
            self._stream = None
            self._error(f"无法打开麦克风：{e}")

    def _read_mic(self):
        latest = None
        while not self._mic_queue.empty():
            latest = self._mic_queue.get_nowait()
        if latest is not None:
            hz = detect_frequency(latest, 44100)
            self._tune = describe_frequency(hz, self._profile.reference_hz) if hz else {"name": "等待稳定音", "cents": 0, "frequency": 0}
            self.changed.emit()

    @Slot()
    def tuneFile(self):
        path, _ = QFileDialog.getOpenFileName(None, "选择单音录音", "", "PCM 录音 (*.wav)")
        if not path: return
        try:
            with wave.open(path) as f:
                if f.getsampwidth() != 2: raise ValueError("请使用 16 位 PCM WAV 单音录音")
                rate = f.getframerate()
                audio = np.frombuffer(f.readframes(min(f.getnframes(), rate * 30)), dtype="<i2").astype(float) / 32768
                audio = audio.reshape(-1, f.getnchannels()).mean(axis=1)
            frequencies = [detect_frequency(audio[i:i+rate//4], rate) for i in range(0, len(audio)-rate//4, rate//4)]
            frequencies = [v for v in frequencies if v]
            if not frequencies: raise ValueError("没有检测到稳定音高，请使用清晰的单音录音")
            self._tune = describe_frequency(float(np.median(frequencies)), self._profile.reference_hz)
            self._message = "已分析单音录音；下方显示多个有效片段的中位音高"
            self.changed.emit()
        except Exception as e: self._error(e)

    def close(self):
        self._conversion_cancel.set()
        self.engine.stop()
        self.hotkeys.close()
        if self._stream:
            self._stream.stop(); self._stream.close()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
