import json
import os
from pathlib import Path
import threading
import time
import wave
import pytest
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("QT_QUICK_BACKEND","software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE","Basic")
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QUrl, QPoint, QObject
from PySide6.QtGui import QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from reed_relay.backend import Backend
from reed_relay.core.profile import Profile
from reed_relay.core.score import Note, Score


@pytest.fixture
def rig(tmp_path, monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR",str(tmp_path))
    backend=Backend("player",no_hotkeys=True)
    backend.audition.setVolume(0)
    yield app,backend,tmp_path
    backend.close()
    app.processEvents()


def wait_for(app, condition, timeout=8):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:
        app.processEvents();time.sleep(.01)
    assert condition()


def test_capture_keyboard_conflict_cancel_mouse_and_combo(rig):
    app,b,d=rig
    b.beginBinding("note:0","音符1")
    # Press X: conflicts with the second note and must not overwrite/save.
    QCoreApplication.sendEvent(app,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_X,Qt.KeyboardModifier.NoModifier))
    assert b.binding.active and b._profile.keys[0]=="Z"
    assert not (d/'profile.json').exists()
    QCoreApplication.sendEvent(app,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_J,Qt.KeyboardModifier.NoModifier))
    assert not b.binding.active and b._profile.keys[0]=="J"
    assert Profile.load(d/'profile.json').keys[0]=="J"
    b.beginBinding("hotkey:toggle","启停")
    QCoreApplication.sendEvent(app,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_F9,Qt.KeyboardModifier.ControlModifier))
    assert b._profile.hotkeys['toggle']=="CTRL+F9"
    b.beginBinding("modifier:0","降调")
    QCoreApplication.sendEvent(app,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Q,Qt.KeyboardModifier.NoModifier))
    b.beginBinding("note:0","音符1")
    b.binding.mouse(1)
    assert b._profile.keys[0]=="MOUSE_LEFT"
    previous=(d/'profile.json').read_bytes()
    b.beginBinding("note:0","音符1")
    QCoreApplication.sendEvent(app,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier))
    assert not b.binding.active and (d/'profile.json').read_bytes()==previous
    b.beginBinding("note:0","音符1")
    QCoreApplication.sendEvent(app,QEvent(QEvent.Type.ApplicationDeactivate))
    assert not b.binding.active
    b.beginBinding("note:0","音符1");b.binding.timer.setInterval(1)
    wait_for(app,lambda:not b.binding.active)


def test_registration_and_disk_failure_keep_saved_and_active_profile(rig,monkeypatch):
    app,b,d=rig
    b._profile.save(d/'profile.json')
    before=(d/'profile.json').read_bytes()
    class Keys:
        ready=True
        error="CTRL+F9 被其他程序占用"
        def start(self,keys): self.keys=keys;self.ready=True
        def close(self): self.ready=False
        def try_start(self,keys): self.ready=False;return False
    b.hotkeys.close();b.hotkeys=Keys();b._no_hotkeys=False
    b.beginBinding('hotkey:toggle','启停')
    b._capture_binding('hotkey:toggle','CTRL+F9')
    assert b.binding.active and '占用' in b.binding.hint
    assert b._profile.hotkeys['toggle']=='F8' and (d/'profile.json').read_bytes()==before
    b.binding.cancel()
    assert b.hotkeys.ready and b.hotkeys.keys['toggle']=='F8'
    b._no_hotkeys=True
    monkeypatch.setattr(Profile,'save',lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    b.beginBinding('note:0','音符1');b._capture_binding('note:0','J')
    assert b._profile.keys[0]=='Z' and (d/'profile.json').read_bytes()==before


def test_pages_load_and_launch_click_does_not_bind_left_mouse(rig):
    app,b,d=rig
    b.loadDemo()
    engine=QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge',b)
    engine.rootContext().setContextProperty('initialPage','settings')
    warnings=[];engine.warnings.connect(lambda values:warnings.extend(str(v) for v in values))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/reed_relay/ui/Main.qml')))
    root=engine.rootObjects()[0]
    wait_for(app,lambda:root.property('pagesReady'))
    assert not warnings, warnings
    def visual_items(item):
        yield item
        for child in item.childItems(): yield from visual_items(child)
    button=next(item for item in visual_items(root.contentItem()) if item.objectName()=='bindNote0')
    center=button.mapToScene(button.boundingRect().center()).toPoint()
    QTest.mouseClick(root,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,center)
    app.processEvents()
    assert b.binding.active and b._profile.keys[0]=='Z'
    QTest.keyClick(root,Qt.Key.Key_J)
    app.processEvents()
    assert not b.binding.active and b._profile.keys[0]=='J'
    root.setProperty('page','audition');app.processEvents()
    assert root.property('pagesReady') and not warnings
    root.hide()


def test_audition_load_pause_resume_seek_loop_and_long_plan(rig):
    app,b,d=rig
    b._score=Score('long',[Note(0,3400,60),Note(3400,400,62)],4000)
    b.scoreChanged.emit()
    b.configureArticulation('rearticulate',35)
    b.audition.setSound(2,'game')
    b.auditionScore()
    wait_for(app,lambda:b.audition._loaded and not b.audition.busy)
    path=b.audition._path
    assert path and path.exists()
    with wave.open(str(path)) as r: assert r.getnframes()/r.getframerate()==pytest.approx(2)
    b.audition.seek(1200)
    assert b.audition.position==pytest.approx(1200,abs=5)
    b.audition.setLoop(True,1000,1800)
    b.audition._want_play=True
    b.audition._position_changed(920)
    assert b.audition.position==pytest.approx(1000,abs=5)
    b.audition.setLoop(False,0,4000)
    b.auditionScore()
    assert not b.audition.playing
    b.auditionScore()
    wait_for(app,lambda:b.audition.playing)
    b.audition.setSound(1,'game')
    b.auditionScore()
    wait_for(app,lambda:b.audition._loaded and not b.audition.busy)
    assert '重复音符' not in b.message
    assert len(b._score.notes)==2 and b._score.notes[0].duration_ms==3400


def test_cancelled_render_cannot_start_after_score_change(rig,monkeypatch):
    import reed_relay.audition as module
    app,b,d=rig
    begun=threading.Event()
    def render(score,path,cancel,*args):
        begun.set()
        cancel.wait(2)
        Path(path).write_bytes(b'late')
    monkeypatch.setattr(module,'synthesize_harmonica',render)
    b.loadDemo();b.auditionScore()
    assert begun.wait(1)
    b.loadDemo()
    wait_for(app,lambda:not b.audition._thread.is_alive())
    app.processEvents()
    assert not b.audition.playing and not b.audition.busy
    assert not list(d.glob('harmonica_*.wav'))
