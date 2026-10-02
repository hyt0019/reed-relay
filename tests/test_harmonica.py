from dataclasses import asdict
import json
import threading
import wave
import numpy as np
import pytest
from reed_relay.core.harmonica import note_audio, synthesize_harmonica, RenderCancelled, sound_bank
from reed_relay.core.profile import Profile, make_plan
from reed_relay.core.score import Note, Score


def test_old_template_migrates_but_custom_mapping_and_bindings_survive():
    data = Profile().to_dict()
    data.pop("pitch_source")
    data["name"] = "默认口琴（待校准）"
    data["keys"][0] = "A"
    migrated = Profile.from_dict(data)
    assert migrated.pitch_source == "sample-inferred" and not migrated.calibrated
    assert migrated.keys[0] == "A"
    data["pitches"][0] = 59
    custom = Profile.from_dict(data)
    assert custom.pitch_source == "custom" and custom.pitches[0] == 59
    data["calibrated"] = True
    assert Profile.from_dict(data).pitch_source == "measured"


def test_switching_never_adds_breath_and_repeat_keeps_next_onset():
    score = Score("切换", [Note(i*500,500,60+i%2*2) for i in range(16)])
    plan = make_plan(score, Profile())
    assert [(n.start_ms,n.duration_ms) for n in plan.notes] == [(n.start_ms,n.duration_ms) for n in score.notes]
    assert not any(i["kind"] == "long-note" for i in plan.issues)
    repeated = Score("连按", [Note(0,500,60),Note(500,500,60)])
    plan = make_plan(repeated, Profile(), speed=2, repeat_gap_ms=35)
    assert plan.notes[0].duration_ms == 430
    assert plan.notes[1].start_ms == 500
    assert repeated.notes[0].duration_ms == 500


def test_long_note_policy_uses_real_duration_and_preserves_original():
    score = Score("长音", [Note(0,4000,60),Note(4000,400,62)])
    original = [asdict(n) for n in score.notes]
    held = make_plan(score, Profile())
    assert held.notes == score.notes
    assert any(i["kind"] == "long-note" for i in held.issues)
    fast = make_plan(score, Profile(), speed=2, long_note_policy="rearticulate")
    assert len(fast.notes) == 2
    split = make_plan(score, Profile(), long_note_policy="rearticulate")
    assert len(split.notes) == 3 and split.notes[1].start_ms == 2000
    assert split.notes[2].start_ms == 4000 and split.notes[-1].end_ms == 4400
    assert [asdict(n) for n in score.notes] == original


def test_harmonica_uses_recording_models_and_block_phase_is_continuous():
    bank = sound_bank()
    assert next(m for m in bank if m["id"] == "normal_c")["takes_used"] == 2
    t = np.arange(44100)/44100
    full = note_audio(60,t,1,mode="game")
    parts = np.r_[note_audio(60,t[:17291],1,mode="game"),note_audio(60,t[17291:],1,mode="game")]
    assert np.allclose(full,parts) and np.isfinite(full).all()
    assert np.sqrt(np.mean(full**2)) > .01
    stable = note_audio(60,t,1)
    spectrum = abs(np.fft.rfft(stable[2205:-2205]))
    freqs = np.fft.rfftfreq(len(stable[2205:-2205]),1/44100)
    fundamental = freqs[(freqs>250)&(freqs<270)][np.argmax(spectrum[(freqs>250)&(freqs<270)])]
    assert abs(fundamental-261.6256) < 2
    assert not np.allclose(full,stable)


def test_speed_changes_duration_not_pitch_and_cancel_is_atomic(tmp_path):
    score = Score("音高", [Note(100,1000,60)],1200)
    for speed in (.5,2):
        path=tmp_path/f"{speed}.wav"
        synthesize_harmonica(score,path,speed=speed)
        with wave.open(str(path)) as r:
            assert r.getnframes() == round(1.2/speed*r.getframerate())
            x=np.frombuffer(r.readframes(r.getnframes()),dtype='<i2').astype(float)
        a=x[round(.25/speed*44100):round(.8/speed*44100)]
        f=np.fft.rfftfreq(len(a),1/44100); spec=abs(np.fft.rfft(a*np.hanning(len(a))))
        selected=(f>245)&(f<275)
        assert abs(f[selected][np.argmax(spec[selected])]-261.6256) < 3
    path=tmp_path/'safe.wav';path.write_bytes(b'previous')
    cancel=threading.Event();cancel.set()
    with pytest.raises(RenderCancelled): synthesize_harmonica(score,path,cancel)
    assert path.read_bytes() == b'previous' and not path.with_name('safe.wav.part').exists()
