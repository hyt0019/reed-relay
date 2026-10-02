import os
from pathlib import Path
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from PySide6.QtCore import QUrl, Qt, QPointF
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from reed_relay.backend import Backend
from reed_relay.core.score import Score, Note
from reed_relay.player.engine import PreviewOutput


@pytest.fixture
def rig(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(tmp_path/'data'))
    backend = Backend('player', no_hotkeys=True)
    backend.audition.setVolume(0)
    yield app, backend, tmp_path
    backend.close()
    app.processEvents()


def wait_for(app, condition, timeout=8):
    until = time.monotonic()+timeout
    while not condition() and time.monotonic() < until:
        app.processEvents()
        time.sleep(.01)
    assert condition()


def load_score(backend, directory, name='Seek', duration=10000):
    path = directory/f'{name}.json'
    Score(name, [Note(0, duration-300, 61), Note(duration-200, 100, 64)], duration).save(path)
    assert backend.loadProjectPath(str(path))
    return path


def test_seek_stop_resume_and_stale_reports_do_not_overwrite_cursor(rig):
    app, b, directory = rig
    load_score(b, directory)
    original = list(b._score.notes)
    b.seekPlayer(1200)
    b.toggle()
    first_output, first_session = b.engine.output, b._player_session
    time.sleep(.05)
    assert first_output.held == {'Z', 'MOUSE_MIDDLE'}
    b.beginPlayerSeek()
    assert b.playerSeeking and not b.running and not first_output.held
    b.toggle()
    assert not b.engine.running
    b.seekPlayer(5200)
    app.processEvents()  # Includes real queued progress, note, and finish events.
    assert b.progress == 5200 and not b.running and not b.playerSeeking
    b.toggle()
    current_session = b._player_session
    b._handle_report('player', (first_session, 'progress', 9999))
    b._handle_report('player', (first_session, 'finished', 'late finish'))
    b._handle_report('player', (first_session, 'note', {'pitch':64, 'key':'C', 'down':True}))
    assert b._player_session == current_session and b.running and b.progress == 5200
    time.sleep(.03)
    b.stop()
    stopped_position = b.progress
    assert 5200 < stopped_position < 5600 and not b.engine.output.held
    b.toggle()
    assert b.engine.position_ms >= stopped_position
    b.stop()
    assert b._score.notes == original


def test_song_change_new_score_and_completed_replay_reset_position(rig):
    app, b, directory = rig
    first = load_score(b, directory, 'First', 400)
    second = load_score(b, directory, 'Second', 500)
    b._add_score(first)
    b._add_score(second)
    b.seekPlayer(200)
    b.toggle()
    output = b.engine.output
    b.stepSong(-1)
    app.processEvents()
    assert b.title == 'First' and b.progress == 0 and not output.held and not b.running
    b.seekPlayer(400)
    b.toggle()
    assert b.engine.position_ms < 100  # At the end, replay starts from zero.
    b.stop()
    b.seekPlayer(390)
    b.toggle()
    wait_for(app, lambda:not b.engine.running)
    app.processEvents()
    assert b.progress == 400
    b.toggle()
    assert b.engine.position_ms < 100
    assert b.loadProjectPath(str(second))
    app.processEvents()
    assert b.title == 'Second' and b.progress == 0 and not b.running
    b.seekPlayer(100)
    b.removeSong(1)
    assert b.progress == 0


def test_seek_keeps_game_countdown_and_focus_guard(rig, monkeypatch):
    import reed_relay.backend as module
    app, b, directory = rig
    load_score(b, directory)
    class Keys:
        ready = True
        def close(self): pass
    b.hotkeys.close()
    b.hotkeys = Keys()
    b._windows = [{'hwnd':123}]
    focused = [True]
    monkeypatch.setattr(module, 'WindowsOutput', PreviewOutput)
    monkeypatch.setattr(module, 'focus_guard', lambda window:lambda:focused[0])
    b.configurePlayer(False, 1., 1., 0, False, False, 0)
    b.seekPlayer(2200)
    b.toggle()
    time.sleep(.03)
    app.processEvents()
    assert b.state == '倒计时' and b.progress == 2200 and b.engine.output.events == []
    b.stop()
    assert b.progress == 2200
    focused[0] = False
    b.configurePlayer(False, 1., 0., 0, False, False, 0)
    b.toggle()
    wait_for(app, lambda:not b.engine.running)
    app.processEvents()
    assert not b.engine.output.events and '失焦' in b.message
    b._target = -1
    b.toggle()
    assert not b.engine.running and '请选择目标游戏窗口' in b.message


def test_audition_and_invalid_position_keep_player_cursor(rig):
    app, b, directory = rig
    load_score(b, directory, duration=1500)
    b.seekPlayer(600)
    for value in (-1, 1501, float('nan'), float('inf')):
        b.seekPlayer(value)
        assert b.progress == 600 and not b.engine.running
    b._media_position(900)
    b.audition.seek(300)
    assert b.progress == 600
    b.auditionScore()
    wait_for(app, lambda:b.audition._loaded)
    b.stopAudio()
    app.processEvents()
    assert b.progress == 600 and not b.engine.running
    b.mode = 'converter'
    b._media_position(400)
    assert b.progress == 400


def test_actual_player_slider_drag_stop_keyboard_seek_and_reset(rig):
    app, b, directory = rig
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', b)
    engine.rootContext().setContextProperty('initialPage', 'main')
    warnings = []
    engine.warnings.connect(lambda values:warnings.extend(str(v) for v in values))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/reed_relay/ui/Main.qml')))
    root = engine.rootObjects()[0]
    wait_for(app, lambda:root.property('pagesReady'))
    def visual(item):
        yield item
        for child in item.childItems(): yield from visual(child)
    def find(name):
        return next(item for item in visual(root.contentItem()) if item.objectName() == name and item.isVisible())
    def click(name):
        item = find(name)
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         item.mapToScene(item.boundingRect().center()).toPoint())
        app.processEvents()
    slider = find('playerSeek')
    assert not slider.isEnabled()
    load_score(b, directory)
    app.processEvents()
    assert slider.isEnabled() and slider.property('value') == 0
    click('playerToggle')
    first_output = b.engine.output
    wait_for(app, lambda:bool(first_output.held))
    def point(fraction):
        return slider.mapToScene(QPointF(slider.width()*fraction, slider.height()/2)).toPoint()
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point(.15))
    app.processEvents()
    assert b.playerSeeking and not b.running and not first_output.held
    QTest.mouseMove(root, point(.6), 20)
    app.processEvents()
    assert 5600 <= slider.property('chosenPosition') <= 6400
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point(.6))
    app.processEvents()
    assert 5600 <= b.progress <= 6400 and not b.playerSeeking and not b.engine.running
    assert slider.property('value') == b.progress
    selected = b.progress
    assert find('playerPosition').property('text').startswith('00:0')
    click('playerToggle')
    assert selected <= b.engine.position_ms < selected+200
    wait_for(app, lambda:bool(b.engine.output.held))
    b.stop()
    click('playerSeek')
    old_position = b.progress
    QTest.keyClick(root, Qt.Key.Key_Right)
    app.processEvents()
    assert b.progress == old_position+100 and not b.engine.running
    click('playerReset')
    assert b.progress == 0 and slider.property('value') == 0
    assert not warnings, warnings
    root.hide()
