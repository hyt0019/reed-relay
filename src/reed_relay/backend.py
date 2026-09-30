from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import uuid
import wave

import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl
from PySide6.QtWidgets import QFileDialog
from reed_relay.core.score import Score, Note, atomic_json, pitch_name, extract_melody
from reed_relay.core.profile import Profile, make_plan
from reed_relay.core.tuning import tone, detect_frequency, describe_frequency
from reed_relay.core.calibration import GuidedCalibration
from reed_relay.player.engine import PlayerEngine, PreviewOutput
from reed_relay.player.windows import Hotkeys, WindowsOutput, windows, focus_guard, held_controls, window_alive, monitor_name


class Backend(QObject):
    changed = Signal()
    scoreChanged = Signal()
    profileChanged = Signal()
    playlistChanged = Signal()
    issuesChanged = Signal()
    windowsChanged = Signal()
    selectionChanged = Signal()
    captureDevicesChanged = Signal()
    calibrationChanged = Signal()
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
        self._auto_continue = False
        self._initial_options = {"speed":100,"delay":3,"transpose":0,"melody":False,"skip":False,"auto_continue":False}
        try:
            pref_path=self.data_dir/"preferences.json"
            if pref_path.exists(): self._initial_options.update(json.loads(pref_path.read_text(encoding="utf-8")))
        except (ValueError,OSError):
            pass
        self._tune, self._stream, self._mic_queue = {}, None, queue.Queue(maxsize=2)
        self._capture_source, self._capture_devices, self._capture_device = "system", [], -1
        self._loopback, self._capture_level, self._last_audio_time = None, 0., 0.
        self._capture_status = "选择游戏正在使用的输出设备，然后开始测音"
        self._busy, self._conversion_progress, self._audio_path, self._waveform = False, 0., "", []
        self._conversion_cancel = threading.Event()
        self._conversion_thread = None
        self._audio_queue, self._selected_note = [], -1
        self._media, self._audio_output = None, None
        self._loop_start, self._loop_end, self._loop_enabled = 0, 0, False
        self._pending_seek = None
        self._no_hotkeys = no_hotkeys
        self._closing = False
        self._calibration = None
        self._calibration_visible = False
        self._calibration_target = None
        self._calibration_monitor, self._calibration_position = "", "top-right"
        self._calibration_focus = lambda: False
        self._calibration_starting = False
        self._calibration_deadline = 0.
        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(40)
        self._calibration_timer.timeout.connect(self._tick_calibration)
        self._overlay_hide_timer = QTimer(self)
        self._overlay_hide_timer.setSingleShot(True)
        self._overlay_hide_timer.timeout.connect(self.hideCalibration)
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
        self._mic_timer.timeout.connect(self._read_tuning)
        if mode == "player" and not no_hotkeys:
            self.hotkeys.start(self._profile.hotkeys)
        self.refreshWindows()
        if mode == "converter":
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._media = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_output.setVolume(.65)
            self._media.setAudioOutput(self._audio_output)
            self._media.positionChanged.connect(self._media_position)
            self._media.mediaStatusChanged.connect(self._media_status)
            self._media.errorOccurred.connect(lambda *args: self._error("试听失败：" + self._media.errorString()))

    @Property(str, constant=True)
    def appMode(self): return self.mode
    @Property(bool, notify=calibrationChanged)
    def calibrationActive(self): return self._calibration is not None and self._calibration.active
    @Property("QVariantMap", notify=calibrationChanged)
    def calibration(self):
        value = self._calibration.snapshot() if self._calibration else {
            "active":False,"phase":"idle","title":"尚未开始","instruction":"","hint":"",
            "last_note":"","step":0,"total":0,"progress":0.,"stability":0.,"optional":False,"paused":False}
        profile = self._calibration.original if self._calibration else self._profile
        return value | {"visible":self._calibration_visible,"monitor":self._calibration_monitor,
                        "position":self._calibration_position,"hotkeys":profile.hotkeys}
    @Property("QVariantMap", constant=True)
    def playbackDefaults(self): return self._initial_options
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
    def listening(self): return self._stream is not None or self._loopback is not None
    @Property(str, notify=changed)
    def captureSource(self): return self._capture_source
    @Property("QVariantList", notify=captureDevicesChanged)
    def captureDevices(self): return self._capture_devices
    @Property(int, notify=changed)
    def captureDevice(self): return self._capture_device
    @Property(float, notify=changed)
    def captureLevel(self): return self._capture_level
    @Property(str, notify=changed)
    def captureStatus(self): return self._capture_status
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
    @Property(int, notify=selectionChanged)
    def selectedNote(self): return self._selected_note
    @Property(int, notify=changed)
    def queuedCount(self): return len(self._audio_queue)
    @Property("QVariantList", notify=scoreChanged)
    def voices(self): return sorted({n.voice for n in self._score.notes})

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
        elif kind == "conversion":
            self._conversion_progress, self._message, info = value
            if info:
                self._waveform = info.get("waveform", self._waveform)
                self._audio_path = info.get("path", self._audio_path)
        elif kind == "converted":
            self._score, path = value
            self._selected_note, self._undo, self._redo = -1, [], []
            self.selectionChanged.emit()
            self._audio_path = self._score.source_file
            self._message = f"已完成并保存：{path}"
            self._check()
            self.scoreChanged.emit()
        elif kind == "job_done": self._busy = False
        elif kind == "synthesized":
            self._media.setSource(QUrl.fromLocalFile(str(value)))
            self._loop_start, self._loop_end, self._loop_enabled = 0, 0, False
            self._media.play()
            for old in self.data_dir.glob("audition_*.wav"):
                if old != value:
                    try: old.unlink()
                    except OSError: pass
        self.changed.emit()

    @Slot(str)
    def _on_hotkey(self, action):
        if self._calibration_visible:
            self.calibrationAction(action)
            return
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
        if not 0 <= index < len(self._playlist): return False
        self.stop()
        try: self._add_score(self._playlist[index]["path"])
        except Exception as e:
            self._error(e)
            return False
        self.changed.emit()
        return True

    @Slot(int)
    def stepSong(self, delta):
        if self._playlist:
            resume=self.engine.running and self._auto_continue
            loaded=self.selectSong((self._selected + delta) % len(self._playlist))
            if resume and loaded: self.toggle()

    @Slot(int)
    def moveSong(self, delta):
        old=self._selected;new=old+delta
        if 0<=old<len(self._playlist) and 0<=new<len(self._playlist):
            self._playlist[old],self._playlist[new]=self._playlist[new],self._playlist[old]
            self._selected=new
            self._save_playlist();self.playlistChanged.emit();self.changed.emit()

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

    @Slot(bool, float, float, int, bool, bool, int, bool)
    def configurePlayer(self, preview, speed, delay, transpose, melody, skip, target, auto_continue=False):
        self._preview, self._speed, self._delay, self._transpose = preview, speed, delay, transpose
        self._melody, self._skip, self._target = melody, skip, target
        self._auto_continue=auto_continue
        try:
            atomic_json(self.data_dir/"preferences.json",{"speed":round(speed*100),"delay":delay,"transpose":transpose,"melody":melody,"skip":skip,"auto_continue":auto_continue})
        except OSError as e: self._message=f"无法保存演奏偏好：{e}"
        self._check()
        self.changed.emit()

    @Slot()
    def toggle(self):
        if self.calibrationActive:
            self._error("请先完成或取消调音引导，再启动演奏")
            return
        if self.engine.running:
            self.stop()
            return
        try:
            if not self._preview and not self._profile.calibrated:
                raise ValueError("请在调音页核对实际音高并确认校准，再启用游戏输入")
            if not self._preview and not self.hotkeys.ready:
                raise ValueError("全局热键尚未就绪，请先解决底部显示的热键冲突")
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
        if self.calibrationActive:
            self._error("调音引导进行中；请先完成或取消")
            return
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
            if self.listening: self.stopTuning()
            import sounddevice as sd
            sd.play(tone(pitch, reference), 44100)
        except Exception as e: self._error(f"参考音播放失败：{e}")

    @Slot()
    def refreshAudioDevices(self):
        previous = self._capture_devices[self._capture_device]["name"] if 0 <= self._capture_device < len(self._capture_devices) else None
        self.stopTuning()
        try:
            from .capture import loopback_devices
            self._capture_devices = loopback_devices()
            self._capture_device = next((i for i,d in enumerate(self._capture_devices) if d["name"]==previous), 0 if self._capture_devices else -1)
            self._capture_status = "请选择游戏正在使用的耳机或扬声器" if self._capture_devices else "未找到可采集的输出设备，请连接耳机/扬声器后刷新"
        except Exception as e:
            self._capture_devices, self._capture_device = [], -1
            self._capture_status = f"无法读取声音设备：{e}"
        self.captureDevicesChanged.emit()
        self.changed.emit()

    @Slot(str)
    def setCaptureSource(self, source):
        if source not in ("system", "microphone"): return
        self.stopTuning()
        self._capture_source = source
        if source == "system": self.refreshAudioDevices()
        else: self._capture_status = "将使用 Windows 默认录音设备"
        self.changed.emit()

    @Slot(int)
    def setCaptureDevice(self, index):
        self.stopTuning()
        self._capture_device = index if 0 <= index < len(self._capture_devices) else -1
        self._capture_status = "设备已选择，点击开始测音"
        self.changed.emit()

    @Slot()
    def stopTuning(self):
        if self.calibrationActive:
            self.cancelCalibration()
            return
        self._stop_capture()

    def _stop_capture(self):
        self._mic_timer.stop()
        stream, loopback = self._stream, self._loopback
        self._stream = self._loopback = None
        self._capture_level, self._tune = 0., {}
        self._capture_status = "测音已停止"
        try:
            if stream:
                try: stream.stop()
                finally: stream.close()
        except Exception as e: self._capture_status = f"关闭麦克风时出现问题：{e}"
        try:
            if loopback: loopback.stop()
        except Exception as e: self._capture_status = f"关闭电脑声音采集时出现问题：{e}"
        while not self._mic_queue.empty():
            self._mic_queue.get_nowait()
        self.changed.emit()

    @Slot()
    def toggleTuning(self):
        if self.listening:
            self.stopTuning()
            return
        try:
            self.stopAudio()
            self._tune, self._capture_level = {}, 0.
            if self._capture_source == "system":
                if not 0 <= self._capture_device < len(self._capture_devices):
                    raise ValueError("请刷新并选择游戏使用的输出设备")
                from .capture import SystemAudioCapture
                capture = SystemAudioCapture(self._capture_devices[self._capture_device])
                capture.start()
                self._loopback = capture
            else:
                import sounddevice as sd
                def callback(data, frames, timing, status):
                    try: self._mic_queue.put_nowait(data.copy())
                    except queue.Full: pass
                self._stream = sd.InputStream(samplerate=44100, channels=1, blocksize=11025, callback=callback)
                self._stream.start()
            self._last_audio_time = time.monotonic()
            self._capture_status = "正在采集电脑声音，请在游戏中弹奏单音" if self._loopback else "正在采集麦克风，请发出稳定单音"
            self._mic_timer.start()
            self.changed.emit()
        except Exception as e:
            self.stopTuning()
            self._capture_status = f"无法开始测音：{e}"
            self._error(self._capture_status)

    def _read_tuning(self):
        latest = None
        rate = 44100
        try:
            if self._loopback:
                latest, rate = self._loopback.latest(), self._loopback.rate
            else:
                while not self._mic_queue.empty():
                    latest = self._mic_queue.get_nowait()
        except Exception as e:
            if self.calibrationActive:
                self._calibration.fail(f"声音采集已中断：{e}；原场景保持不变")
                self._end_calibration()
            else: self.stopTuning()
            self._capture_status = f"采集已中断：{e}"
            self._error(self._capture_status)
            return
        if latest is not None:
            self._last_audio_time = time.monotonic()
            rms = float(np.sqrt(np.mean(np.asarray(latest, dtype=float)**2)))
            self._capture_level = max(0., min(1., (20*np.log10(max(rms, 1e-6))+60)/60))
            hz = detect_frequency(latest, rate)
            reference = self._calibration.original.reference_hz if self.calibrationActive else self._profile.reference_hz
            self._tune = describe_frequency(hz, reference) if hz else {"name": "等待稳定音", "cents": 0, "frequency": 0}
            self._capture_status = "已检测到单音；可填写到下方对应按键" if hz else ("声音较弱或静音，请检查所选设备与游戏音量" if rms<.003 else "已收到声音，请单独弹奏一个音并减少伴奏")
            if self.calibrationActive: self._tick_calibration(self._tune)
        elif time.monotonic() - self._last_audio_time > 1:
            self._tune = {"name": "等待声音", "cents": 0, "frequency": 0}
            self._capture_level = 0.
            self._capture_status = "尚未收到声音，请确认游戏输出到所选设备；设备变化后请刷新"
            if self.calibrationActive: self._tick_calibration(self._tune)
        self.changed.emit()

    @Slot(str, int, str)
    def startCalibration(self, raw, window_index, position):
        if self.calibrationActive: return
        try:
            if self._busy: raise ValueError("请等待音频处理完成，再开始引导")
            if self._no_hotkeys: raise ValueError("此启动模式禁用了全局热键，无法开始游戏内引导")
            if not 0 <= window_index < len(self._windows): raise ValueError("请先选择目标游戏窗口")
            profile = Profile.from_dict(json.loads(raw))
            target = dict(self._windows[window_index])
            if not window_alive(target): raise ValueError("目标窗口已关闭，请刷新窗口列表")
            self.stop()
            self.stopTuning()
            self.toggleTuning()
            if not self.listening: return
            self._overlay_hide_timer.stop()
            self._calibration = GuidedCalibration(profile, time.monotonic())
            self._calibration_target = target
            self._calibration_focus = focus_guard(target)
            self._calibration_monitor = monitor_name(target)
            self._calibration_position = position if position in ("top-left","top-right","bottom-center") else "top-right"
            self._calibration_visible, self._calibration_starting = True, True
            self._calibration_deadline = time.monotonic()+3
            self.hotkeys.start(profile.hotkeys)
            self._calibration.hint = "正在准备全局热键，请切回游戏"
            self._calibration_timer.start()
            self._message = "调音引导已启动，请按悬浮提示操作；全部完成后自动保存"
            self.calibrationChanged.emit()
            self.changed.emit()
        except Exception as e:
            if self.calibrationActive:
                self._calibration.fail(str(e))
                self._end_calibration()
            else: self._stop_capture()
            self._error(e)

    def _tick_calibration(self, sample=None):
        if not self.calibrationActive: return
        now = time.monotonic()
        try:
            if self._calibration_starting:
                if not self.hotkeys.ready:
                    if now>self._calibration_deadline:
                        raise RuntimeError("全局热键未就绪："+self._hotkey_status)
                    return
                self._calibration_starting = False
                self._calibration.deadline = now+3
            if not self.hotkeys.ready: raise RuntimeError("全局热键已失效，请重新开始引导")
            if not self.listening: raise RuntimeError("声音采集已停止")
            if not window_alive(self._calibration_target): raise RuntimeError("目标游戏窗口已关闭")
            self._calibration.tick(now, held_controls(self._calibration.controls), self._calibration_focus(), sample)
            if self._calibration.phase == "done":
                result = self._calibration.result
                self._profile.save(self.data_dir/"profile.before-calibration.json")
                result.save(self.data_dir/"profile.json")
                self._profile = result
                self.profileChanged.emit()
                self._check()
                self._calibration.hint = "校准已保存，可以继续留在游戏中；提示稍后自动收起"
                self._end_calibration()
            else: self.calibrationChanged.emit()
        except Exception as e:
            self._calibration.fail(f"{e}；原场景保持不变")
            self._end_calibration()

    def _end_calibration(self):
        self._calibration_timer.stop()
        self._calibration_starting = False
        self._stop_capture()
        self._message = self._calibration.hint
        if not self._closing:
            self._overlay_hide_timer.start(8000)
        self.calibrationChanged.emit()
        self.changed.emit()

    @Slot(str)
    def calibrationAction(self, action):
        if not self._calibration: return
        if not self.calibrationActive:
            if action == "emergency": self.hideCalibration()
            return
        if action == "emergency": self.cancelCalibration(); return
        if action == "toggle": self._calibration.toggle_pause()
        elif action == "previous": self._calibration.rewind()
        elif action == "next": self._calibration.skip(time.monotonic())
        self.calibrationChanged.emit()

    @Slot()
    def cancelCalibration(self):
        if self.calibrationActive:
            self._calibration.cancel()
            self._end_calibration()
        else: self.hideCalibration()

    @Slot()
    def hideCalibration(self):
        if self.calibrationActive: return
        self._calibration_visible = False
        self._overlay_hide_timer.stop()
        if not self._closing and not self._no_hotkeys:
            if self.mode == "player": self.hotkeys.start(self._profile.hotkeys)
            else: self.hotkeys.close()
        self.calibrationChanged.emit()

    def previewCalibration(self):
        """Screenshot-only preview: no recording, key polling or file changes."""
        self._calibration = GuidedCalibration(self._profile, time.monotonic())
        self._calibration.phase = "listen"
        self._calibration.hint = "按住提示按键约 1 秒，识别稳定后自动进入下一步"
        self._calibration_visible = True
        self.calibrationChanged.emit()

    @Slot()
    def tuneFile(self):
        self.stopTuning()
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

    @Slot()
    def openAudio(self):
        if self._busy: return
        paths, _ = QFileDialog.getOpenFileNames(None, "选择音频（可多选）", "", "音频 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.aiff *.wma)")
        if paths: self.setAudioFiles(json.dumps(paths))

    @Slot(str)
    def setAudioFiles(self, raw):
        if self._busy: return
        try:
            paths = [QUrl(v).toLocalFile() if str(v).startswith("file:") else str(v) for v in json.loads(raw)]
            paths = [str(Path(p).resolve()) for p in paths if Path(p).is_file()]
            if not paths: raise ValueError("没有找到有效音频文件")
            self._audio_queue, self._audio_path = paths, paths[0]
            self._waveform = []
            self._message = f"已选择 {len(paths)} 个文件，点击开始转谱"
            self.changed.emit()
        except Exception as e: self._error(e)

    @Slot(bool)
    def convert(self, melody):
        if self._busy: return
        if not self._audio_queue:
            self._error("请先选择音频文件")
            return
        self.stopAudio()
        self._busy, self._conversion_progress = True, 0
        self._conversion_cancel.clear()
        paths = list(self._audio_queue)
        def worker():
            try:
                from .converter.transcribe import transcribe
                from .converter.audio import Cancelled
                failures=[]
                for i, path in enumerate(paths):
                    def progress(value, message, info):
                        data = (info or {}) | {"path": path}
                        self.report.emit("conversion", ((i+value)/len(paths), f"{i+1}/{len(paths)}  {message}", data))
                    try:
                        score = transcribe(path, melody, self._conversion_cancel, progress)
                        target = self.data_dir / "conversions" / (Path(path).stem[:100] + "_" + uuid.uuid4().hex[:6] + ".reedscore.json")
                        score.save(target)
                        self.report.emit("converted", (score, str(target)))
                    except Cancelled:
                        raise
                    except Exception as e:
                        failures.append(f"{Path(path).name}: {e}")
                if failures:
                    self.report.emit("error",f"批量完成：成功 {len(paths)-len(failures)}/{len(paths)}；失败："+"；".join(failures))
            except Exception as e: self.report.emit("error", str(e))
            finally: self.report.emit("job_done", None)
        self._conversion_thread = threading.Thread(target=worker, daemon=True)
        self._conversion_thread.start()
        self.changed.emit()

    @Slot()
    def cancelConversion(self):
        self._conversion_cancel.set()
        self._error("正在取消；当前推断片段结束后停止")

    @Slot()
    def openProject(self):
        if self._busy: return
        path, _ = QFileDialog.getOpenFileName(None, "打开曲谱工程", str(self.data_dir), "曲谱 (*.json *.mid *.midi)")
        if path: self.loadProjectPath(path)

    @Slot(str)
    def loadProjectPath(self, path):
        try:
            self.stopAudio()
            score = Score.from_midi(path) if path.lower().endswith((".mid", ".midi")) else Score.load(path)
            self._score, self._audio_path = score, score.source_file
            self._undo, self._redo, self._selected_note = [], [], -1
            self.selectionChanged.emit()
            self._waveform = score.metadata.get("waveform", [])
            self._audio_queue = [score.source_file] if Path(score.source_file).is_file() else []
            self._check()
            self.scoreChanged.emit()
            self._message = "已打开曲谱；点击音符可校对与试听"
            self.changed.emit()
        except Exception as e: self._error(e)

    @Slot()
    def recoverProject(self):
        path = self.data_dir / "autosave.reedscore.json"
        if path.exists(): self.loadProjectPath(str(path))
        else: self._error("没有可恢复的自动保存工程")

    @Slot()
    def relinkAudio(self):
        if self._busy: return
        path,_=QFileDialog.getOpenFileName(None,"重新关联当前曲谱的原音频","","音频 (*.mp3 *.wav *.flac *.ogg *.m4a)")
        if path:
            self.stopAudio()
            self._score.source_file=path
            self._audio_path=path
            self._audio_queue=[path]
            self._message="已重新关联原音频"
            self._edited()

    @Slot(int)
    def selectNote(self, index):
        self._selected_note = index if 0 <= index < len(self._score.notes) else -1
        self.selectionChanged.emit()
        self.changed.emit()

    def _remember(self):
        self._undo.append(list(self._score.notes))
        self._undo = self._undo[-50:]
        self._redo.clear()

    def _edited(self):
        self._score.validate()
        self._check()
        try: self._score.save(self.data_dir / "autosave.reedscore.json")
        except Exception as e: self._message = f"自动保存失败：{e}"
        self.scoreChanged.emit()
        self.selectionChanged.emit()
        self.changed.emit()

    @Slot(int, float, float, int)
    def editNote(self, index, start, duration, pitch):
        if self._busy: return
        try:
            if not 0 <= index < len(self._score.notes): raise ValueError("请先选择音符")
            new = replace(self._score.notes[index], start_ms=start, duration_ms=duration, midi_pitch=pitch, cents=0)
            self._remember()
            self._score.notes[index] = new
            self._score.validate()
            self._selected_note = next(i for i,n in enumerate(self._score.notes) if n.id==new.id)
            self._message = "已修改音符，原始转写备份保留"
            self._edited()
        except Exception as e: self._error(e)

    @Slot(float, float, int)
    def addNote(self, start, duration, pitch):
        if self._busy: return
        try:
            new = Note(start, duration, pitch)
            self._remember(); self._score.notes.append(new)
            self._score.validate()
            self._selected_note = next(i for i,n in enumerate(self._score.notes) if n.id==new.id)
            self._edited()
        except Exception as e: self._error(e)

    @Slot(int)
    def deleteNote(self, index):
        if self._busy or not 0 <= index < len(self._score.notes): return
        self._remember(); self._score.notes.pop(index)
        self._selected_note = min(index, len(self._score.notes)-1)
        self._edited()

    @Slot(int)
    def splitNote(self, index):
        if self._busy or not 0 <= index < len(self._score.notes): return
        try:
            n = self._score.notes[index]
            a = replace(n, duration_ms=n.duration_ms/2)
            b = replace(n, start_ms=n.start_ms+n.duration_ms/2, duration_ms=n.duration_ms/2, id=uuid.uuid4().hex[:12])
            self._remember(); self._score.notes[index:index+1] = [a,b]
            self._edited()
        except Exception as e: self._error(e)

    @Slot(int)
    def mergeNote(self, index):
        if self._busy or not 0 <= index < len(self._score.notes)-1: return
        try:
            a,b = self._score.notes[index:index+2]
            if a.midi_pitch != b.midi_pitch: raise ValueError("只能合并相邻的同音高音符")
            new = replace(a, duration_ms=max(a.end_ms,b.end_ms)-a.start_ms)
            self._remember(); self._score.notes[index:index+2] = [new]
            self._edited()
        except Exception as e: self._error(e)

    @Slot()
    def undo(self):
        if self._undo and not self._busy:
            self._redo.append(list(self._score.notes)); self._score.notes=self._undo.pop(); self._selected_note=-1; self._edited()

    @Slot()
    def redo(self):
        if self._redo and not self._busy:
            self._undo.append(list(self._score.notes)); self._score.notes=self._redo.pop(); self._selected_note=-1; self._edited()

    @Slot(bool)
    def changeReduction(self, melody):
        if self._busy: return
        self._remember()
        if not self._score.original_notes: self._score.original_notes=list(self._score.notes)
        source = self._score.original_notes
        self._score.notes = extract_melody(source) if melody else list(source)
        self._selected_note=-1
        self._edited()

    @Slot(str)
    def selectVoice(self, voice):
        if self._busy: return
        if any(n.voice==voice for n in self._score.notes):
            self._remember()
            if not self._score.original_notes: self._score.original_notes=list(self._score.notes)
            self._score.notes=[n for n in self._score.notes if n.voice==voice]
            self._selected_note=-1; self._edited()

    @Slot(str)
    def exportScore(self, kind):
        if self._busy or not self._score.notes: return
        suffix, filter_text = {"json": (".reedscore.json", "曲谱工程 (*.reedscore.json)"), "midi": (".mid", "MIDI (*.mid)"), "text": (".txt", "简谱 (*.txt)")}[kind]
        path, _ = QFileDialog.getSaveFileName(None, "导出曲谱", self._score.title+suffix, filter_text)
        if path:
            if not path.lower().endswith(suffix): path+=suffix
            try:
                {"json": self._score.save, "midi": self._score.export_midi, "text": self._score.export_text}[kind](path)
                self._error(f"已导出：{path}")
            except Exception as e: self._error(e)

    def _media_position(self, position):
        self._progress=position
        if self._loop_end and position>=self._loop_end:
            if self._loop_enabled: self._media.setPosition(self._loop_start)
            else: self._media.pause()
        self.changed.emit()

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pending_seek is not None:
            self._media.setPosition(self._pending_seek)
            self._pending_seek = None
            self._media.play()

    @Slot(bool)
    def auditionOriginal(self, loop):
        if self._media is None: return
        source = self._score.source_file or self._audio_path
        if not Path(source).is_file():
            self._error("找不到原音频；请先重新选择原文件")
            return
        self._media.stop()
        self._loop_start,self._loop_end=0,0
        if 0<=self._selected_note<len(self._score.notes):
            n=self._score.notes[self._selected_note]
            self._loop_start=max(0,int(n.start_ms)-150)
            self._loop_end=int(n.end_ms)+150
        self._loop_enabled=loop
        url=QUrl.fromLocalFile(source)
        if self._media.source()==url:
            self._media.setPosition(self._loop_start);self._media.play()
        else:
            self._pending_seek=self._loop_start
            self._media.setSource(url)

    @Slot()
    def auditionScore(self):
        if self._media is None or self._busy or not self._score.notes: return
        self.stopAudio(); self._busy=True; self._conversion_cancel.clear()
        score=replace(self._score, notes=list(self._score.notes))
        if 0<=self._selected_note<len(score.notes):
            n=score.notes[self._selected_note]
            score=replace(score,notes=[replace(n,start_ms=0)],duration_ms=n.duration_ms)
        path=self.data_dir / ("audition_"+uuid.uuid4().hex[:8]+".wav")
        def worker():
            try:
                from .converter.audio import synthesize
                synthesize(score,path,self._conversion_cancel)
                self.report.emit("synthesized",path)
            except Exception as e: self.report.emit("error",str(e))
            finally: self.report.emit("job_done",None)
        self._conversion_thread=threading.Thread(target=worker,daemon=True)
        self._conversion_thread.start()
        self.changed.emit()

    @Slot()
    def stopAudio(self):
        self._loop_end=0
        self._pending_seek=None
        if self._media: self._media.stop()

    def close(self):
        self._closing = True
        self.cancelCalibration()
        self._calibration_timer.stop()
        self._overlay_hide_timer.stop()
        self._calibration_visible = False
        self.calibrationChanged.emit()
        self._conversion_cancel.set()
        self.stopAudio()
        if self._conversion_thread and self._conversion_thread.is_alive():
            self._conversion_thread.join(timeout=2)
        self.engine.stop()
        self.hotkeys.close()
        self.stopTuning()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
