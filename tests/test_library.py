import json
import os
from pathlib import Path
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from PySide6.QtWidgets import QApplication, QFileDialog
from reed_relay.core.score import Score, Note
from reed_relay.library import ScoreLibrary, read_score, default_library
from reed_relay.backend import Backend


def test_scan_keeps_invalid_files_visible_and_refreshes_changed_scores(tmp_path):
    directory = tmp_path/'曲库'
    Score('清晨', [Note(123, 456, 61)], 700).save(directory/'清晨.reedscore.json')
    Score('MIDI', [Note(12, 500, 74)], 1500).export_midi(directory/'MIDI.MID')
    (directory/'broken.mid').write_bytes(b'not midi')
    (directory/'ignore.wav').write_bytes(b'not a score')
    library = ScoreLibrary(directory)
    entries = library.scan()
    assert len(entries) == 3
    assert sum(bool(e['error']) for e in entries) == 1
    midi = next(e for e in entries if e['filename'] == 'MIDI.MID')
    assert midi['duration'] == pytest.approx(1500) and midi['minimum_pitch'] == 74
    Score('Updated title', [Note(100, 900, 67)]).save(directory/'清晨.reedscore.json')
    assert next(e for e in library.scan() if e['filename'] == '清晨.reedscore.json')['title'] == 'Updated title'


def test_import_is_self_contained_deduplicates_and_keeps_same_name_variants(tmp_path):
    first, second = tmp_path/'first/同名.reedscore.json', tmp_path/'second/同名.reedscore.json'
    Score('One', [Note(100, 400, 60, cents=13)], 700).save(first)
    Score('Two', [Note(200, 600, 62)], 900).save(second)
    library = ScoreLibrary(tmp_path/'library')
    original_bytes = first.read_bytes()
    imported = library.import_score(first)
    assert imported.created and imported.path.read_bytes() == original_bytes
    duplicate = library.import_score(first)
    assert not duplicate.created and duplicate.path == imported.path
    renamed = tmp_path/'renamed.json'
    renamed.write_bytes(original_bytes)
    assert library.import_score(renamed).path == imported.path
    variant = library.import_score(second)
    assert variant.created and variant.path.name == '同名 (2).reedscore.json'
    assert imported.path.read_bytes() == original_bytes
    first.unlink(); second.unlink()
    assert read_score(imported.path).notes[0].cents == 13
    assert read_score(variant.path).notes[0].midi_pitch == 62


def test_invalid_and_empty_imports_do_not_create_library(tmp_path):
    library = ScoreLibrary(tmp_path/'library')
    bad = tmp_path/'bad.mid'; bad.write_bytes(b'not midi')
    with pytest.raises(Exception): library.import_score(bad)
    empty = tmp_path/'empty.json'; Score('Empty').save(empty)
    with pytest.raises(ValueError, match='没有可用音符'): library.import_score(empty)
    assert not library.directory.exists()


def test_default_uses_user_example_folder_or_selected_data_directory(tmp_path, monkeypatch):
    import reed_relay.library as module
    monkeypatch.delenv('REED_RELAY_DATA_DIR', raising=False)
    monkeypatch.setattr(module, 'application_root', lambda:tmp_path/'program')
    data = tmp_path/'selected-data'
    assert default_library(data) == data/'演奏库'
    example = tmp_path/'program/样例文件/示例曲谱'; example.mkdir(parents=True)
    assert default_library(data) == example
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(data))
    assert default_library(data) == data/'演奏库'


@pytest.mark.parametrize('mode', ['player', 'converter'])
def test_backend_partial_import_loads_midi_without_audio_conversion_and_persists_folder(tmp_path, monkeypatch, mode):
    app = QApplication.instance() or QApplication([])
    data = tmp_path/'data'
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(data))
    backend = Backend(mode, no_hotkeys=True)
    directory = tmp_path/'示例曲谱'; directory.mkdir()
    backend.setLibraryPath(str(directory))
    source = tmp_path/'song.mid'
    Score('Known', [Note(100, 400, 61), Note(500, 350, 64)], 1300).export_midi(source)
    bad = tmp_path/'bad.mid'; bad.write_bytes(b'broken')
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *args:([str(source),str(bad)], ''))
    backend.openScores()
    assert '成功 1/2' in backend.message and 'bad.mid' in backend.message
    assert len(backend.libraryEntries) == 1
    assert [n.midi_pitch for n in backend._score.notes] == [61,64]
    assert backend._score.notes[0].start_ms == pytest.approx(100)
    assert backend._score.duration_ms == pytest.approx(1300)
    assert not backend._audio_path and not backend._audio_queue
    copied = directory/source.name
    source.unlink()
    assert backend.openLibraryScore(str(copied))
    if mode == 'player':
        backend.addLibraryToPlaylist()
        assert len(backend.playlist) == 1 and backend.libraryEntries[0]['in_playlist']
        backend.removeSong(0)
        assert copied.exists() and not backend.libraryEntries[0]['in_playlist']
    backend.close()
    second = Backend(mode, no_hotkeys=True)
    assert Path(second.libraryPath) == directory and len(second.libraryEntries) == 1
    second.close()


def test_cancel_and_failed_directory_change_preserve_current_work(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(tmp_path/'data'))
    backend = Backend('player', no_hotkeys=True)
    backend.loadDemo()
    before = list(backend._score.notes)
    playlist = list(backend.playlist)
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *args:([], ''))
    backend.openScores()
    assert backend._score.notes == before and backend.playlist == playlist
    previous = backend.libraryPath
    target = tmp_path/'new-library'; target.mkdir()
    import reed_relay.backend as module
    monkeypatch.setattr(module, 'atomic_json', lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    backend.setLibraryPath(str(target))
    assert backend.libraryPath == previous and '未切换' in backend.message
    backend.close()


def test_midi_tempo_changes_and_overlaps_survive_import(tmp_path):
    import mido
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage('set_tempo', tempo=500000),
        mido.Message('note_on', note=60, velocity=80),
        mido.Message('note_on', note=64, velocity=90, time=240),
        mido.MetaMessage('set_tempo', tempo=1000000, time=240),
        mido.Message('note_off', note=60, time=480),
        mido.Message('note_off', note=64, time=240)]))
    source = tmp_path/'tempo.mid'; midi.save(source)
    imported = ScoreLibrary(tmp_path/'library').import_score(source)
    notes = read_score(imported.path).notes
    assert [(n.midi_pitch, n.start_ms, n.end_ms) for n in notes] == [(60,0,1500),(64,250,2000)]
