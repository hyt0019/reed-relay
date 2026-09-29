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
    backend.setAudioFiles(json.dumps([str(audio)]))
    assert backend.queuedCount==1
    backend.convert(True)
    until=time.monotonic()+30
    while backend.busy and time.monotonic()<until:
        app.processEvents();time.sleep(.01)
    assert not backend.busy, backend.message
    assert backend._score.notes, backend.message
    assert backend._waveform
    assert list((tmp_path/"data/conversions").glob("*.json"))
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
