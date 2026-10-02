from dataclasses import replace
import pytest
from reed_relay.core.score import Note, Score, extract_melody
from reed_relay.core.melody import repair_melody, select_melody


def test_temporal_path_ignores_brief_competitor_but_follows_sustained_change():
    sustained = Note(0, 1000, 60, confidence=.55)
    transient = Note(400, 12, 84, confidence=.9)
    next_note = Note(1000, 400, 64, confidence=.8)
    notes = [sustained, transient, next_note]
    result = extract_melody(notes)
    assert [(n.midi_pitch, n.start_ms, n.end_ms) for n in result] == [(60, 0, 1000), (64, 1000, 1400)]
    assert notes == [sustained, transient, next_note]
    Score('path', result).validate()


def test_repair_removes_fragments_connects_small_gaps_and_keeps_rests():
    notes = [Note(0, 200, 60), Note(200, 12, 84), Note(225, 200, 62), Note(1000, 200, 64)]
    result = repair_melody(notes, 80, 50)
    assert [n.midi_pitch for n in result] == [60, 62, 64]
    assert result[0].end_ms == 225 and result[1].start_ms == 225
    assert result[1].end_ms == 425 and result[2].start_ms == 1000
    assert notes[0].end_ms == 200
    assert all(a.end_ms <= b.start_ms for a, b in zip(result, result[1:]))


def test_fast_notes_and_repeated_attacks_can_be_preserved():
    notes = [Note(0, 40, 60), Note(40, 40, 60), Note(80, 40, 62)]
    assert repair_melody(notes, 0, 0) == notes
    merged = repair_melody(notes, 0, 0, True)
    assert [n.duration_ms for n in merged] == [80, 40]
    assert merged[-1].start_ms == 80
    assert not repair_melody(notes, 80, 0)


def test_same_source_fragments_rejoin_and_polyphony_becomes_valid():
    original = Note(0, 300, 60)
    parts = [replace(original, duration_ms=100, id=original.id+'_0'),
             Note(100, 12, 84), replace(original, start_ms=112, duration_ms=188, id=original.id+'_2')]
    result = repair_melody(parts, 80, 50)
    assert len(result) == 1 and result[0].duration_ms == 300
    poly = repair_melody([original, Note(30, 250, 67)], 0, 0)
    Score('poly', poly).validate()
    assert all(a.end_ms <= b.start_ms for a, b in zip(poly, poly[1:]))


def test_zero_settings_preserve_real_rests_and_no_transposition():
    notes = [Note(0, 100, 59, cents=-13), Note(150, 110, 60, cents=9)]
    assert repair_melody(notes, 0, 0) == notes
    with pytest.raises(ValueError): repair_melody(notes, float('nan'), 50)


@pytest.mark.parametrize('scale', [.5, 1., 2.])
def test_strong_bass_does_not_replace_upper_melody(scale):
    pitches = [67, 69, 71, 72, 71, 69, 67, 64]
    melody = [Note(i*300*scale, 300*scale, p, confidence=.45) for i, p in enumerate(pitches)]
    bass = [Note(i*600*scale, 600*scale, 36+i%3, confidence=.9) for i in range(4)]
    result = select_melody(melody+bass)
    assert [n.midi_pitch for n in result] == pitches
    assert [(n.start_ms, n.end_ms) for n in result] == [(n.start_ms, n.end_ms) for n in melody]


def test_dense_high_ornaments_do_not_cut_sustained_inner_melody():
    melody = [Note(0, 1000, 65, confidence=.45), Note(1000, 1000, 67, confidence=.45)]
    high = [Note(150+i*70, 45, 84+i%3, confidence=.95) for i in range(25)]
    result = select_melody(melody+high+[Note(0, 2000, 36, confidence=.8)])
    assert [(n.midi_pitch, n.start_ms, n.end_ms) for n in result] == [(65, 0, 1000), (67, 1000, 2000)]


def test_melody_rests_are_not_filled_with_bass():
    notes = [Note(0, 500, 72, confidence=.7), Note(1000, 500, 74, confidence=.7),
             Note(0, 1500, 36, confidence=.95)]
    assert [(n.midi_pitch, n.start_ms, n.end_ms) for n in select_melody(notes)] == [(72, 0, 500), (74, 1000, 1500)]


def test_range_filter_keeps_raw_candidates_and_fast_monophonic_attacks():
    melody = [Note(0, 40, 60), Note(40, 40, 60), Note(80, 40, 62)]
    notes = melody+[Note(0, 120, 36)]
    assert select_melody(notes, minimum_pitch=60, maximum_pitch=72) == melody
    assert len(notes) == 4
    assert not select_melody(notes, minimum_pitch=90)
    with pytest.raises(ValueError): select_melody(notes, minimum_pitch=72, maximum_pitch=60)
    with pytest.raises(ValueError): select_melody(notes, maximum_pitch=float('nan'))
