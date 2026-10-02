import json
import os
from pathlib import Path
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from reed_relay.core.score import Note, Score, atomic_json
from reed_relay.storage import Storage
import reed_relay.storage as storage_module


@pytest.fixture
def locations(tmp_path, monkeypatch):
    monkeypatch.delenv('REED_RELAY_DATA_DIR', raising=False)
    root, old = tmp_path/'program', tmp_path/'old-appdata'
    root.mkdir()
    monkeypatch.setattr(storage_module, 'application_root', lambda: root)
    monkeypatch.setattr(storage_module, 'legacy_directory', lambda: old)
    return root, old


def test_portable_default_migrates_legacy_and_preserves_originals(locations):
    root, old = locations
    project = old/'conversions/song.json'
    Score('saved', [Note(0, 200, 60)]).save(project)
    atomic_json(old/'playlist.json', [str(project)])
    (old/'harmonica_old.wav').write_bytes(b'temporary')
    storage = Storage()
    assert storage.directory == root/'local-data'
    copied = storage.directory/'conversions/song.json'
    assert Score.load(copied).title == 'saved' and project.exists()
    assert json.loads((storage.directory/'playlist.json').read_text(encoding='utf-8')) == [str(copied)]
    assert not (storage.directory/'harmonica_old.wav').exists()
    assert Storage().directory == storage.directory


def test_selected_directory_persists_and_internal_paths_are_rewritten(locations):
    root, _ = locations
    storage = Storage()
    source = storage.directory/'song.json'
    Score('song', [Note(0, 100, 60)], source_file=str(storage.directory/'source.wav')).save(source)
    atomic_json(storage.directory/'playlist.json', [str(source)])
    target = root/'custom'
    storage.choose(target)
    assert source.exists()
    assert Score.load(target/'song.json').source_file == str(target/'source.wav')
    assert Storage().directory == target


def test_conflicts_and_invalid_targets_do_not_change_active_directory(locations):
    root, _ = locations
    storage = Storage()
    atomic_json(storage.directory/'preferences.json', {'volume':1})
    target = root/'occupied'
    atomic_json(target/'preferences.json', {'volume':2})
    pointer = storage.locator.read_bytes()
    with pytest.raises(ValueError, match='已有不同'):
        storage.choose(target)
    assert storage.locator.read_bytes() == pointer and storage.directory == root/'local-data'
    assert json.loads((target/'preferences.json').read_text()) == {'volume':2}
    with pytest.raises(ValueError): storage.choose(storage.directory/'nested')


def test_pointer_write_failure_rolls_back_copies_but_keeps_existing_target(locations, monkeypatch):
    root, _ = locations
    storage = Storage()
    atomic_json(storage.directory/'profile.json', {'key':'Z'})
    target = root/'destination'
    target.mkdir()
    keep = target/'keep.txt'; keep.write_text('keep')
    pointer = storage.locator.read_bytes()
    monkeypatch.setattr(storage_module, 'atomic_json', lambda *_: (_ for _ in ()).throw(OSError('read-only')))
    with pytest.raises(OSError): storage.choose(target)
    assert storage.directory == root/'local-data' and storage.locator.read_bytes() == pointer
    assert not (target/'profile.json').exists() and keep.read_text() == 'keep'
    assert (storage.directory/'profile.json').exists()


def test_environment_override_is_respected_without_writing_locator(locations, monkeypatch):
    root, _ = locations
    fixed = root/'controlled'
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(fixed))
    storage = Storage()
    assert storage.directory == fixed and storage.fixed
    assert not storage.locator.exists()
    with pytest.raises(ValueError, match='启动配置'): storage.choose(root/'other')


def test_backend_switch_routes_autosave_audition_and_second_module(locations):
    from reed_relay.backend import Backend
    root, _ = locations
    app = QApplication.instance() or QApplication([])
    backend = Backend('converter', no_hotkeys=True)
    backend.loadDemo()
    old = backend.data_dir
    target = root/'user-choice'
    backend.setStoragePath(str(target))
    assert backend.data_dir == target and backend.audition.directory == target
    assert all(Path(item['path']).is_relative_to(target) for item in backend._playlist)
    backend.editNote(0, 0, 300, 61)
    assert Score.load(target/'autosave.reedscore.json').notes[0].midi_pitch == 61
    assert (old/'晨风.reedscore.json').exists()
    second = Backend('player', no_hotkeys=True)
    assert second.data_dir == target and second._playlist
    second.close(); backend.close(); app.processEvents()


def test_legacy_collision_is_reported_without_overwrite_or_c_drive_fallback(locations):
    root, old = locations
    atomic_json(old/'profile.json', {'source':'old'})
    atomic_json(root/'local-data/profile.json', {'source':'new'})
    storage = Storage()
    assert storage.directory == root/'local-data'
    assert '失败' in storage.notice
    assert json.loads((storage.directory/'profile.json').read_text()) == {'source':'new'}


def test_export_suggestions_stay_under_selected_directory(locations):
    from reed_relay.storage import suggested_file
    root, _ = locations
    path = Path(suggested_file(root, '../C:/artist/曲谱', '.reedscore.json'))
    assert path.parent == root and '/' not in path.name and ':' not in path.name
    assert Path(suggested_file(root, 'CON', '.json')).name == '_CON.json'


def test_explicit_first_location_never_falls_back_after_write_failure(locations, monkeypatch):
    root, old = locations
    atomic_json(old/'profile.json', {'key':'Z'})
    target = root/'first-choice'
    monkeypatch.setattr(storage_module, 'atomic_json', lambda *_: (_ for _ in ()).throw(OSError('read-only')))
    with pytest.raises(OSError): Storage(initial_directory=target)
    assert not (root/'local-data').exists() and not (root/'storage-location.json').exists()
    assert not (target/'profile.json').exists() and (old/'profile.json').exists()


def test_actual_gui_directory_picker_repair_undo_and_export(locations, monkeypatch):
    from reed_relay.backend import Backend
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog
    root_dir, _ = locations
    app = QApplication.instance() or QApplication([])
    backend = Backend('converter', no_hotkeys=True)
    original = [Note(0, 200, 60), Note(200, 12, 84), Note(225, 200, 62)]
    backend._score = Score('点击修整', list(original), 600)
    backend.scoreChanged.emit()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', backend)
    engine.rootContext().setContextProperty('initialPage', 'storage')
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(str(v) for v in values))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/reed_relay/ui/Main.qml')))
    window = engine.rootObjects()[0]
    app.processEvents()
    assert window.property('pagesReady') and not warnings
    def items(item):
        yield item
        for child in item.childItems(): yield from items(child)
    def click(name):
        button = next(item for item in items(window.contentItem()) if item.objectName() == name and item.isVisible())
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         button.mapToScene(button.boundingRect().center()).toPoint())
        app.processEvents()
    target = root_dir/'selected-by-dialog'
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_: str(target))
    click('chooseStorage')
    assert backend.data_dir == target
    path_field = next(item for item in items(window.contentItem()) if item.objectName() == 'storagePath')
    assert path_field.property('text') == str(target)
    window.setProperty('page', 'audition'); app.processEvents()
    click('repairApply')
    assert len(backend._score.notes) == 2 and backend._score.notes[0].end_ms == 225
    assert backend._score.original_notes == original and backend.duration == 600
    assert Score.load(target/'autosave.reedscore.json').notes == backend._score.notes
    click('repairUndo')
    assert backend._score.notes == original
    backend.configureRepair(0, 0, False)
    backend.repairCurrent()
    assert backend._score.notes == original
    destination = target/'export.reedscore.json'
    suggested = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (suggested.append(args[2]) or str(destination), ''))
    backend.exportScore('json')
    assert Path(suggested[0]).parent == target and Score.load(destination).notes == original
    backend.configureRepair(500, 0, False)
    backend.repairCurrent()
    assert backend._score.notes == original and '没有音符' in backend.message
    assert not warnings, warnings
    window.hide(); backend.close(); app.processEvents()
