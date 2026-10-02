import threading
import numpy as np
import pytest
from reed_relay.core.score import Note, Score, extract_melody
from reed_relay.converter.audio import decode, synthesize, Cancelled
from reed_relay.converter.transcribe import transcribe, unwrap_with_times


def test_window_time_mapping_keeps_late_notes_aligned():
    # Window hops are not an integer multiple of output frame hops.
    blocks = np.zeros((101,172,1))
    output = {key:[blocks] for key in ("note","onset","contour")}
    result, times = unwrap_with_times(output,36164,256,22050,165.08,15)
    assert times[100*142] == pytest.approx(100*36164/22050)
    assert times[-1] == 165.08
    assert len(times) == len(result["note"])+1
    assert np.all(np.diff(times)>0)


def test_melody_float_boundaries_do_not_make_zero_length_notes():
    notes=[Note(.1,.2,60),Note(.3,.4,64)]
    result=extract_melody(notes)
    assert len(result)==2
    assert all(n.duration_ms>=.1 for n in result)


def test_decode_and_synthesis_preserve_duration(tmp_path):
    score=Score("合成",[Note(500,500,60),Note(1500,500,64)],2500)
    path=tmp_path / "合成.wav"
    synthesize(score,path)
    audio,rate=decode(path)
    assert rate==22050
    assert len(audio)==round(score.duration_ms/1000*rate)
    assert np.max(np.abs(audio[:rate//2]))==0
    assert np.max(np.abs(audio[rate//2:rate]))>.1
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled): decode(path,cancel)


def test_real_model_known_pitches_and_late_timing(tmp_path):
    pytest.importorskip("basic_pitch")
    score=Score("已知音高",[Note(500,700,60),Note(1700,700,64),Note(60500,700,67)],62000)
    path=tmp_path / "known.wav"
    synthesize(score,path)
    result=transcribe(path,melody=False)
    assert result.original_notes
    assert all(n.cents == 0 for n in result.notes)
    assert result.metadata['pitch_bends_third_semitone']
    for expected in score.notes:
        candidates=[n for n in result.notes if n.midi_pitch==expected.midi_pitch]
        assert candidates, f"Missing pitch {expected.midi_pitch}"
        matched=min(candidates,key=lambda n:abs(n.start_ms-expected.start_ms))
        assert abs(matched.start_ms-expected.start_ms)<100
        assert abs(matched.end_ms-expected.end_ms)<150
    saved=tmp_path / "known.reedscore.json"
    result.save(saved)
    assert Score.load(saved).original_notes==result.original_notes


def test_real_model_mixture_selects_melody_instead_of_stronger_bass(tmp_path):
    pytest.importorskip('basic_pitch')
    melody = [Note(300+i*450, 420, p, velocity=110) for i, p in enumerate([67,69,71,72,71,69,67,64])]
    bass = [Note(300+i*900, 890, 36+i%3, velocity=127) for i in range(4)]
    path = tmp_path/'mixture.wav'
    synthesize(Score('Known mixture', melody+bass, 4200), path)
    result = transcribe(path)
    assert any(n.midi_pitch < 48 for n in result.original_notes)
    # The model can miss tones; the selector must not fill these with bass.
    matches = sum(any(n.midi_pitch == m.midi_pitch and n.start_ms <= m.start_ms+200 < n.end_ms
                      for n in result.notes) for m in melody)
    assert matches >= 6
    assert all(n.midi_pitch in {m.midi_pitch for m in melody} for n in result.notes)
    assert all(n.cents == 0 for n in result.notes)
