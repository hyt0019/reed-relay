"""Brief native Windows overlay check; never captures audio or sends input."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

import reed_relay
from reed_relay.backend import Backend
from reed_relay.core.score import atomic_json
from reed_relay.overlay import position_overlay


def main():
    if os.name != "nt": raise RuntimeError("This diagnostic needs Windows")
    root = Path(__file__).resolve().parents[1]
    os.environ["REED_RELAY_DATA_DIR"] = str(root/"local-data/overlay-check")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    app.setQuitOnLastWindowClosed(False)
    backend = Backend("player", no_hotkeys=True)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", backend)
    engine.load(QUrl.fromLocalFile(str(Path(reed_relay.__file__).parent/"ui/CalibrationOverlay.qml")))
    if not engine.rootObjects(): return 1
    window = engine.rootObjects()[0]
    position_overlay(window, "", "top-right")
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
    api.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    hwnd = int(window.winId())
    foreground = api.GetForegroundWindow()
    backend.previewCalibration()

    def check():
        styles = api.GetWindowLongPtrW(hwnd, -20)
        result = {
            "topmost":bool(styles & 0x8),
            "mouse_passthrough":bool(styles & 0x20),
            "no_activate":bool(styles & 0x08000000),
            "foreground_unchanged":api.GetForegroundWindow() == foreground,
            "visible":window.isVisible(),
        }
        result["passed"] = all(result.values())
        atomic_json(root/"output/overlay-check.json", result)
        print(result)
        backend.close()
        window.hide()
        app.exit(0 if result["passed"] else 1)

    QTimer.singleShot(800, check)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
