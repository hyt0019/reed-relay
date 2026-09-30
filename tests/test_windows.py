import ctypes
import os
import pytest
from reed_relay.player import windows
from reed_relay.core.profile import Profile
from reed_relay.core.score import Score,Note


def test_native_input_layout_and_mouse_flags(monkeypatch):
    if os.name != "nt": pytest.skip("Windows ABI test")
    captured=[]
    class API:
        def MapVirtualKeyW(self,*args): return 0x2C
        def SendInput(self,count,data,size):
            event=ctypes.cast(data,ctypes.POINTER(windows.INPUT)).contents
            captured.append((event.type,event.mi.dwFlags if event.type==0 else event.ki.dwFlags))
            assert size==40 if ctypes.sizeof(ctypes.c_void_p)==8 else size==28
            return 1
    monkeypatch.setattr(windows,"user32",lambda:API())
    output=windows.WindowsOutput()
    output.send("MOUSE_MIDDLE",True)
    output.send("Z",True)
    output.release_all()
    assert captured[:2]==[(0,32),(1,8)]
    assert (0,64) in captured and (1,10) in captured
    assert not output.held


def test_reserved_hotkey_is_rejected():
    profile=Profile();profile.hotkeys["emergency"]="F12"
    with pytest.raises(ValueError,match="保留"):
        profile.validate()


def test_short_midi_note_does_not_end_with_held_note(tmp_path):
    import mido
    path=tmp_path/"short.mid"
    Score("极短音",[Note(0,.1,60)]).export_midi(path)
    events=[m.type for m in mido.MidiFile(path) if m.type in ("note_on","note_off")]
    assert events==["note_on","note_off"]
