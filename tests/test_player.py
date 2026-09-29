import time
from reed_relay.core.score import Score, Note
from reed_relay.core.profile import Profile, make_plan
from reed_relay.player.engine import PlayerEngine, PreviewOutput


def wait_stopped(engine):
    until = time.monotonic() + 2
    while engine.running and time.monotonic() < until:
        time.sleep(.01)
    assert not engine.running


def test_stop_releases_note_and_modifier():
    out = PreviewOutput()
    engine = PlayerEngine()
    engine.start(make_plan(Score("测试", [Note(0, 5000, 61)]), Profile()), out)
    time.sleep(.05)
    assert out.held == {"Z", "MOUSE_MIDDLE"}
    engine.stop()
    assert not out.held


def test_focus_loss_releases_everything():
    state = [True]
    messages = []
    out = PreviewOutput()
    engine = PlayerEngine(lambda *args: messages.append(args))
    engine.start(make_plan(Score("测试", [Note(0, 5000, 61)]), Profile()), out, focused=lambda: state[0])
    time.sleep(.03)
    state[0] = False
    wait_stopped(engine)
    assert not out.held
    assert "失焦" in messages[-1][1]


def test_exception_releases_previously_pressed_keys():
    class FailingOutput(PreviewOutput):
        def send(self, key, down):
            if key == "Z" and down: raise RuntimeError("test rejection")
            super().send(key, down)
    out = FailingOutput()
    engine = PlayerEngine()
    engine.start(make_plan(Score("测试", [Note(0, 100, 61)]), Profile()), out)
    wait_stopped(engine)
    assert not out.held


def test_countdown_cancellation_sends_nothing():
    out = PreviewOutput()
    engine = PlayerEngine()
    engine.start(make_plan(Score("测试", [Note(0, 100, 61)]), Profile()), out, delay=1)
    engine.stop()
    assert out.events == []


def test_adjacent_notes_and_timing():
    out = PreviewOutput()
    engine = PlayerEngine()
    engine.start(make_plan(Score("测试", [Note(0, 80, 60), Note(100, 80, 64)]), Profile()), out)
    wait_stopped(engine)
    assert [(k, d) for _, k, d in out.events] == [("Z", True), ("Z", False), ("C", True), ("C", False)]
    assert .08 <= out.events[2][0] - out.events[0][0] <= .16
