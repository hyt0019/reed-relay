import time
import pytest
from reed_relay.core.score import Score, Note
from reed_relay.core.profile import Profile, make_plan
from reed_relay.player.engine import PlayerEngine, PreviewOutput, events_from_position


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


def test_seek_restores_sustained_note_and_modifiers_without_changing_plan():
    score = Score("定位", [Note(0, 1000, 61), Note(1200, 100, 64)])
    plan = make_plan(score, Profile())
    original_events, original_notes = list(plan.events), list(score.notes)
    events = events_from_position(plan, 700)
    assert [(e.at_ms, e.key, e.down) for e in events] == [
        (700, "MOUSE_MIDDLE", True), (700, "Z", True),
        (1000, "Z", False), (1000, "MOUSE_MIDDLE", False),
        (1200, "C", True), (1300, "C", False)]
    assert events[1].note_id == score.notes[0].id and events[1].pitch == 61
    assert plan.events == original_events and score.notes == original_notes


def test_seek_exact_boundary_only_starts_the_new_note_once():
    plan = make_plan(Score("切音", [Note(0, 100, 61), Note(100, 100, 62)]), Profile())
    events = events_from_position(plan, 100)
    assert [(e.at_ms, e.key, e.down) for e in events] == [(100, "X", True), (200, "X", False)]
    assert events_from_position(plan, 200) == []


def test_seek_repeat_release_gap_is_kept():
    plan = make_plan(Score("同音", [Note(0, 100, 60), Note(100, 100, 60)]), Profile())
    assert [(e.at_ms, e.down) for e in events_from_position(plan, 80)] == [(100, True), (200, False)]
    assert [(e.at_ms, e.down) for e in events_from_position(plan, 100)] == [(100, True), (200, False)]


@pytest.mark.parametrize("offset", [-1, 201, float("nan"), float("inf"), True])
def test_invalid_seek_cannot_start_or_send_inputs(offset):
    engine, out = PlayerEngine(), PreviewOutput()
    with pytest.raises(ValueError):
        engine.start(make_plan(Score("定位", [Note(0, 200, 60)]), Profile()), out, start_ms=offset)
    assert not engine.running and not out.events


def test_seek_skips_earlier_notes_and_scales_remaining_time():
    out, reports = PreviewOutput(), []
    plan = make_plan(Score("定位", [Note(0, 80, 64), Note(10000, 300, 61)]), Profile())
    engine = PlayerEngine(lambda *args: reports.append(args))
    engine.start(plan, out, speed=2, start_ms=10100)
    wait_stopped(engine)
    assert [(k, d) for _, k, d in out.events] == [
        ("MOUSE_MIDDLE", True), ("Z", True), ("Z", False), ("MOUSE_MIDDLE", False)]
    assert .07 <= out.events[2][0] - out.events[1][0] < .25
    positions = [value for kind, value in reports if kind == "progress"]
    assert positions[0] == 10100 and positions[-1] == plan.duration_ms
    assert positions == sorted(positions) and not out.held


def test_seek_into_rest_keeps_wait_until_next_onset():
    out, engine = PreviewOutput(), PlayerEngine()
    plan = make_plan(Score("休止", [Note(0, 80, 60), Note(10000, 80, 64)]), Profile())
    begun = time.perf_counter()
    engine.start(plan, out, start_ms=9850)
    time.sleep(.03)
    assert out.events == []
    wait_stopped(engine)
    assert [(k, d) for _, k, d in out.events] == [("C", True), ("C", False)]
    assert .12 <= out.events[0][0] - begun < .4


def test_seek_countdown_cancel_preserves_cursor_and_releases_on_later_stop():
    engine, out = PlayerEngine(), PreviewOutput()
    plan = make_plan(Score("定位", [Note(0, 5000, 61)]), Profile())
    engine.start(plan, out, delay=1, start_ms=2000)
    engine.stop()
    assert not out.events and engine.position_ms == 2000
    engine.start(plan, out, start_ms=2000)
    time.sleep(.03)
    engine.stop()
    assert engine.position_ms > 2000 and not out.held


def test_seek_at_end_finishes_without_input_and_run_callback_is_captured():
    engine, out, reports = PlayerEngine(), PreviewOutput(), []
    plan = make_plan(Score("末尾", [Note(0, 100, 61)]), Profile())
    engine.start(plan, out, start_ms=100, report=lambda *args: reports.append(args))
    wait_stopped(engine)
    assert not out.events and engine.position_ms == 100
    assert reports[-1] == ("finished", "演奏结束")
