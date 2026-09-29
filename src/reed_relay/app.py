from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from .backend import Backend


def run(mode):
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot")
    parser.add_argument("--page", default="main")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-hotkeys", action="store_true")
    parser.add_argument("--score")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    QQuickStyle.setStyle("Basic")
    app.setOrganizationName("ReedRelay")
    app.setApplicationName("风箱" if mode == "player" else "听谱")
    font_family = "Microsoft YaHei"
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families: font_family = families[0]
    app.setFont(QFont(font_family, 10))
    backend = Backend(mode, no_hotkeys=args.no_hotkeys or bool(args.screenshot))
    if args.demo: backend.loadDemo()
    if args.score: backend.loadProjectPath(args.score)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", backend)
    engine.rootContext().setContextProperty("initialPage", args.page)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "Main.qml")))
    if not engine.rootObjects():
        backend.close()
        return 1
    app.aboutToQuit.connect(backend.close)
    if args.screenshot:
        def capture():
            destination = Path(args.screenshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                ok = engine.rootObjects()[0].grabWindow().save(str(destination))
                app.exit(0 if ok else 2)
            except Exception:
                app.exit(2)
        QTimer.singleShot(1200, capture)
    return app.exec()


def player_main(): return run("player")
def converter_main(): return run("converter")


if __name__ == "__main__":
    mode = "converter" if "--converter" in sys.argv else "player"
    if "--converter" in sys.argv: sys.argv.remove("--converter")
    sys.exit(run(mode))
