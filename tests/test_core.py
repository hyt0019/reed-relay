from dataclasses import replace
import json
import numpy as np
import pytest
from reed_relay.core.score import Note, Score, extract_melody
from reed_relay.core.profile import Profile, make_plan
from reed_relay.core.tuning import describe_frequency, detect_frequency, frequency_for, tone


def test_score_roundtrip_preserves_all_pitches_and_timing(tmp_path):
    notes = [Note(23.5, 217.3, 61), Note(350, 500, 88)]
    path = tmp_path / "中文.reedscore.json"
    Score("原调", notes).save(path)
    result = Score.load(path)
    assert result.notes == notes
    assert result.duration_ms == 850


@pytest.mark.parametrize("values", [{"duration_ms": -1}, {"midi_pitch": 128}, {"confidence": float("nan")}, {"midi_pitch": 60.2}])
def test_rejects_invalid_notes(values):
    with pytest.raises(ValueError):
        Note(**({"start_ms": 0, "duration_ms": 100, "midi_pitch": 60} | values))


def test_midi_roundtrip_keeps_absolute_pitch_and_timing(tmp_path):
    original = Score("测试", [Note(10, 249, 49), Note(421, 387, 85)], bpm=87, duration_ms=2000)
    path = tmp_path / "a.mid"
    original.export_midi(path)
    result = Score.from_midi(path)
    for a, b in zip(original.notes, result.notes):
        assert a.midi_pitch == b.midi_pitch
        assert abs(a.start_ms - b.start_ms) < 1
        assert abs(a.duration_ms - b.duration_ms) < 1
    assert result.duration_ms == pytest.approx(2000)


def test_profile_roundtrip_and_conflicts(tmp_path):
    profile = Profile().validate()
    path = tmp_path / "scene.json"
    profile.save(path)
    assert Profile.load(path).mapping() == profile.mapping()
    profile.keys[0] = "F8"
    with pytest.raises(ValueError, match="冲突"):
        profile.validate()


def test_mouse_modifiers_release_before_next_pitch():
    score = Score("时序", [Note(0, 200, 61), Note(200, 200, 60)])
    plan = make_plan(score, Profile())
    assert plan.playable
    same_time = [e for e in plan.events if e.at_ms == 200]
    assert [(e.key, e.down) for e in same_time] == [("Z", False), ("MOUSE_MIDDLE", False), ("Z", True)]


def test_out_of_range_and_overlap_are_not_silently_changed():
    score = Score("冲突", [Note(0, 200, 60), Note(100, 200, 67), Note(400, 100, 110)])
    original = list(score.notes)
    plan = make_plan(score, Profile())
    assert not plan.playable
    assert {i["kind"] for i in plan.issues} == {"overlap", "range"}
    assert score.notes == original
    reduced = extract_melody(score.notes)
    assert all(a.end_ms <= b.start_ms for a, b in zip(reduced, reduced[1:]))
    assert score.notes == original


@pytest.mark.parametrize("pitch", [40, 48, 60, 69, 84])
def test_tuning_known_notes(pitch):
    audio = tone(pitch, 442, seconds=.4)
    hz = detect_frequency(audio, 44100)
    assert hz is not None
    observed = describe_frequency(hz, 442)
    assert observed["pitch"] == pitch
    assert abs(observed["cents"]) < 2


def test_tuner_silence_and_strong_second_harmonic():
    assert detect_frequency(np.zeros(11025), 44100) is None
    t = np.arange(11025) / 44100
    audio = .05 * np.sin(2 * np.pi * 220 * t) + .2 * np.sin(2 * np.pi * 440 * t)
    assert detect_frequency(audio, 44100) == pytest.approx(220, abs=1)
