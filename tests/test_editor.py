import json
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from reed_relay.backend import Backend
from reed_relay.core.score import Note,Score


def test_editor_undo_restore_and_autosave(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR",str(tmp_path))
    backend=Backend("converter",no_hotkeys=True)
    original=[Note(0,400,60),Note(400,400,60)]
    source=tmp_path / "original.json"
    Score("编辑",list(original),original_notes=list(original)).save(source)
    backend.loadProjectPath(str(source))
    backend.editNote(0,0,300,61)
    assert backend._score.notes[0].midi_pitch==61
    assert backend._score.original_notes==original
    backend.undo()
    assert backend._score.notes==original
    backend.redo()
    assert backend._score.notes[0].midi_pitch==61
    backend.changeReduction(False)
    backend.mergeNote(0)
    assert len(backend._score.notes)==1 and backend._score.notes[0].duration_ms==800
    backend.splitNote(0)
    assert len(backend._score.notes)==2
    assert Score.load(tmp_path/"autosave.reedscore.json").notes==backend._score.notes
    backend.close()


def test_gui_audio_queue_completes_in_worker(tmp_path,monkeypatch):
    import time
    from reed_relay.converter.audio import synthesize
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR",str(tmp_path/"data"))
    audio=tmp_path/"queue.wav"
    synthesize(Score("queue",[Note(300,800,64)],1500),audio)
    backend=Backend("converter",no_hotkeys=True)
    corrupt=tmp_path/"broken.wav"
    corrupt.write_bytes(b"not an audio file")
    backend.setAudioFiles(json.dumps([str(corrupt),str(audio)]))
    assert backend.queuedCount==2
    backend.convert(True)
    until=time.monotonic()+30
    while backend.busy and time.monotonic()<until:
        app.processEvents();time.sleep(.01)
    assert not backend.busy, backend.message
    assert backend._score.notes, backend.message
    assert backend._waveform
    assert list((tmp_path/"data/conversions").glob("*.json"))
    assert "成功 1/2" in backend.message
    backend.close()


def test_invalid_edit_and_profile_do_not_replace_good_data(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR",str(tmp_path))
    backend=Backend("player",no_hotkeys=True)
    backend.loadDemo()
    notes=list(backend._score.notes)
    backend.editNote(0,-1,300,60)
    assert backend._score.notes==notes
    profile=backend.profile
    profile["keys"][0]="F8"
    backend.saveProfile(json.dumps(profile))
    assert backend._profile.keys[0]=="Z"
    backend.close()


def test_missing_next_song_stops_without_restarting_previous(tmp_path, monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv("REED_RELAY_DATA_DIR",str(tmp_path))
    backend=Backend("player",no_hotkeys=True)
    backend.loadDemo()
    backend._playlist.append({"path":str(tmp_path/"missing.json"),"title":"Missing","duration":1000})
    backend._auto_continue=True
    backend.toggle()
    assert backend.engine.running
    restarted=[]
    monkeypatch.setattr(backend,"toggle",lambda:restarted.append(True))
    backend.stepSong(1)
    assert not backend.engine.running
    assert not restarted
    backend.close()


def test_melody_range_reextract_legacy_tuning_undo_and_empty_guard(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(tmp_path))
    backend = Backend('converter', no_hotkeys=True)
    bass = Note(0, 800, 36, confidence=.9)
    melody = [Note(0, 400, 60, cents=100/3), Note(400, 400, 62, cents=13)]
    original = [bass, *melody]
    metadata = {'engine':'Spotify Basic Pitch 0.4.0 / ONNX',
                'pitch_bends_third_semitone':{n.id:[1,1,1] for n in melody}}
    path = tmp_path/'legacy.json'
    Score('Legacy', [bass], 800, original_notes=original, metadata=metadata).save(path)
    backend.loadProjectPath(str(path))
    backend.configureMelody(60, 72)
    assert backend._score.notes == [bass]
    backend.changeReduction(True)
    selected = list(backend._score.notes)
    assert [n.midi_pitch for n in selected] == [60, 62]
    assert [n.cents for n in selected] == [0, 13]
    assert backend._score.original_notes == original
    assert Score.load(tmp_path/'autosave.reedscore.json').notes == selected
    backend.undo()
    assert backend._score.notes == [bass]
    backend.redo()
    assert backend._score.notes == selected
    backend.configureMelody(90, 100)
    undo_count = len(backend._undo)
    backend.changeReduction(True)
    assert backend._score.notes == selected and len(backend._undo) == undo_count
    assert '没有旋律候选' in backend.message
    backend.configureMelody(72, 60)
    assert backend.melodyDefaults == {'minimum':90, 'maximum':100}
    backend.close()
    second = Backend('player', no_hotkeys=True)
    assert second.melodyDefaults == {'minimum':90, 'maximum':100}
    second.close()
