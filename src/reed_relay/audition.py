"""Shared audition transport. Rendering and GUI transport have separate lifetimes."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from .core.harmonica import synthesize_harmonica, RenderCancelled


class Audition(QObject):
    changed = Signal()
    message = Signal(str)
    _rendered = Signal(int, str, str)
    _progress = Signal(int, float)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.65)
        self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self._position_changed)
        self.player.playbackStateChanged.connect(lambda _: self.changed.emit())
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(lambda *_: self._failed(self.player.errorString()))
        self._rendered.connect(self._finish)
        self._progress.connect(self._update_progress)
        self._generation, self._cancel, self._thread = 0, threading.Event(), None
        self._busy, self._fraction, self._signature, self._path = False, 0., "", None
        self._speed, self._mode, self._duration, self._position = 1., "clean", 0., 0.
        self._loop, self._start, self._end = False, 0., 0.
        self._want_play, self._closed, self._loaded = False, False, False
        self._seeking = False
        self._seek_after_load = 0.
        self._owned_paths = set()

    @Property(bool, notify=changed)
    def busy(self): return self._busy
    @Property(float, notify=changed)
    def fraction(self): return self._fraction
    @Property(bool, notify=changed)
    def playing(self): return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    @Property(str, notify=changed)
    def status(self):
        if self._busy: return f"正在生成口琴试听 {self._fraction:.0%}"
        if self.playing: return "试听中"
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState: return "已暂停"
        return "准备试听"
    @Property(float, notify=changed)
    def position(self): return self._position
    @Property(float, notify=changed)
    def duration(self): return self._duration
    @Property(float, notify=changed)
    def speed(self): return self._speed
    @Property(str, notify=changed)
    def mode(self): return self._mode
    @Property(float, notify=changed)
    def volume(self): return self.output.volume()
    @Property(bool, notify=changed)
    def looping(self): return self._loop
    @Property(float, notify=changed)
    def rangeStart(self): return self._start
    @Property(float, notify=changed)
    def rangeEnd(self): return self._end

    @Slot(float)
    def setVolume(self, value):
        self.output.setVolume(max(0., min(1., value))); self.changed.emit()

    @Slot(float, str)
    def setSound(self, speed, mode):
        if not .25 <= speed <= 2 or mode not in {"clean", "game"}: return
        if (speed, mode) != (self._speed, self._mode):
            self.stop()
            self._signature = ""
            self._speed, self._mode = speed, mode
            self.changed.emit()

    @Slot(bool, float, float)
    def setLoop(self, enabled, start, end):
        if start < 0 or end < 0 or (end and end <= start):
            self.message.emit("循环终点须晚于起点"); return
        self._loop, self._start, self._end = enabled, start, end
        if self._loop and (self._position < start or (end and self._position >= end)):
            self.seek(start)
        self.changed.emit()

    def reset_score(self, duration):
        self.stop()
        self._signature = ""
        self._duration, self._position = duration, 0.
        self._start, self._end, self._loop = 0., duration, False
        self.changed.emit()

    def set_directory(self, directory):
        self.stop()
        self.player.setSource(QUrl())
        self._loaded = False
        self._signature = ''
        self.directory = Path(directory)

    def play(self, score):
        if not score.notes: self.message.emit("先打开一份曲谱再试听"); return
        score = replace(score, notes=list(score.notes))
        signature = hashlib.sha256(json.dumps([[(n.start_ms,n.duration_ms,n.midi_pitch,n.cents,n.velocity) for n in score.notes], score.duration_ms,score.reference_hz,self._speed,self._mode]).encode()).hexdigest()
        if self._busy: self.stop(); return
        if signature == self._signature and self._loaded and self._path and self._path.exists():
            if self.playing:
                self._want_play = False; self.player.pause()
            else:
                self._want_play = True
                if self._position >= (self._end or self._duration)-5:
                    self.seek(self._start if self._loop else 0)
                self.player.play()
            return
        self.stop()
        self._duration = score.duration_ms
        if self._end > self._duration or self._start >= self._duration:
            self._start,self._end = 0.,self._duration
        self._seek_after_load = self._start if self._loop else min(self._position, max(0,self._duration-1))
        self._signature, self._busy, self._fraction = signature, True, 0.
        self._want_play, self._loaded = True, False
        generation, cancel = self._generation, self._cancel
        speed, mode = self._speed, self._mode
        path = self.directory / ("harmonica_"+uuid.uuid4().hex+".wav")
        def render():
            last = [0.]
            def progress(value):
                now=time.monotonic()
                if now-last[0] > .08 or value == 1:
                    last[0]=now
                    if not self._closed: self._progress.emit(generation,value)
            error = ""
            try: synthesize_harmonica(score,path,cancel,speed,mode,progress)
            except RenderCancelled: error = "cancelled"
            except Exception as e: error = str(e)
            if cancel.is_set():
                path.unlink(missing_ok=True)
            if not self._closed: self._rendered.emit(generation,str(path),error)
            else: path.unlink(missing_ok=True)
        self._thread = threading.Thread(target=render,daemon=True)
        self._thread.start(); self.changed.emit()

    @Slot(int, float)
    def _update_progress(self, generation, value):
        if generation == self._generation and self._busy:
            self._fraction = value; self.changed.emit()

    @Slot(int, str, str)
    def _finish(self, generation, path, error):
        if self._closed or generation != self._generation:
            Path(path).unlink(missing_ok=True); return
        self._busy = False
        if error:
            if error != "cancelled": self._failed(error)
            return
        old = self._path
        self._path = Path(path)
        self._owned_paths.add(self._path)
        self.player.setSource(QUrl.fromLocalFile(path))
        if old and old != self._path:
            try:
                old.unlink(missing_ok=True)
                self._owned_paths.discard(old)
            except OSError: pass
        self.changed.emit()

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._loaded = True
            self.seek(self._seek_after_load)
            if self._want_play: self.player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._loop and self._want_play:
                self.seek(self._start); self.player.play()
            else:
                self._want_play=False
                self._position=self._duration
                self.changed.emit()

    def _position_changed(self, milliseconds):
        if self._seeking: return
        self._position=min(self._duration,milliseconds*self._speed)
        if self._loop and self._want_play and self._end and self._position >= self._end:
            self.seek(self._start)
        self.changed.emit()

    @Slot(float)
    def seek(self, position):
        target=max(0.,min(self._duration,position))
        self._seeking=True
        try: self.player.setPosition(round(target/self._speed))
        finally: self._seeking=False
        self._position=target
        self.changed.emit()

    @Slot()
    def stop(self):
        self._cancel.set()
        self._generation+=1
        self._cancel=threading.Event()
        self._want_play,self._busy=False,False
        self.player.stop()
        self.changed.emit()

    def _failed(self, error):
        self._want_play,self._busy=False,False
        self._signature=""
        self.message.emit("试听失败："+error); self.changed.emit()

    def close(self):
        self._closed=True
        self.stop()
        if self._thread: self._thread.join(timeout=2)
        self.player.setSource(QUrl())
        for path in self._owned_paths:
            try: path.unlink(missing_ok=True)
            except OSError: pass
