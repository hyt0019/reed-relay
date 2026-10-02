import os
from pathlib import Path
import time
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from PySide6.QtCore import QUrl, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog
from reed_relay.backend import Backend
from reed_relay.core.score import Note, Score


@pytest.mark.parametrize('mode', ['player', 'converter'])
def test_actual_library_import_search_preview_open_and_folder_choice(tmp_path, monkeypatch, mode):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(tmp_path/'data'))
    backend = Backend(mode, no_hotkeys=True)
    backend.audition.setVolume(0)
    directory = tmp_path/'library'; directory.mkdir()
    backend.setLibraryPath(str(directory))
    first, second = tmp_path/'first.json', tmp_path/'second.mid'
    Score('First', [Note(100,400,60)], 1200).save(first)
    Score('Second', [Note(200,500,64)], 1400).export_midi(second)
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *args:([str(first), str(second)], ''))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', backend)
    engine.rootContext().setContextProperty('initialPage', 'library')
    warnings = []; engine.warnings.connect(lambda values:warnings.extend(str(v) for v in values))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/reed_relay/ui/Main.qml')))
    root = engine.rootObjects()[0]
    app.processEvents()
    assert root.property('pagesReady') and not warnings
    def visual(item):
        yield item
        for child in item.childItems(): yield from visual(child)
    def find(name):
        return next(item for item in visual(root.contentItem()) if item.objectName() == name and item.isVisible())
    def click(name):
        item = find(name)
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         item.mapToScene(item.boundingRect().center()).toPoint())
        app.processEvents()
    click('libraryImport')
    assert find('librarySongs').property('count') == 2
    search = find('librarySearch')
    click('librarySearch')
    for key in (Qt.Key.Key_F, Qt.Key.Key_I, Qt.Key.Key_R, Qt.Key.Key_S, Qt.Key.Key_T): QTest.keyClick(root, key)
    app.processEvents()
    assert find('librarySongs').property('count') == 1
    click('libraryPreview0')
    assert root.property('page') == 'audition' and backend.title == 'First'
    until = time.monotonic()+8
    while not backend.audition._loaded and time.monotonic()<until:
        app.processEvents(); time.sleep(.01)
    assert backend.audition._loaded and not warnings
    backend.stopAudio()
    click('libraryNavigation')
    click('libraryOpen0')
    assert root.property('page') == 'main' and backend.title == 'First'
    click('libraryNavigation')
    other = tmp_path/'other'; other.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args:str(other))
    click('libraryChoose')
    assert find('libraryPath').property('text') == str(other)
    assert find('librarySongs').property('count') == 0 and len(list(directory.iterdir())) == 2
    assert not warnings
    root.hide(); backend.close(); app.processEvents()
