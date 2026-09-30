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
    parser.add_argument("--overlay-demo", action="store_true", help="仅显示调音悬浮窗示例，不采集或保存")
    parser.add_argument("--page", default="main")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-hotkeys", action="store_true")
    parser.add_argument("--score")
    parser.add_argument("--transcribe")
    parser.add_argument("--check-loopback", action="store_true", help="播放短参考音并验证电脑声音采集，需 --output")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.check_loopback:
        if not args.output: parser.error("--check-loopback 需要 --output 诊断路径")
        from .core.score import atomic_json
        try:
            from .capture import check_loopback
            atomic_json(args.output, check_loopback())
            return 0
        except Exception as e:
            atomic_json(args.output, {"passed": False, "error": str(e)})
            return 1
    if args.transcribe:
        if mode != "converter" or not args.output:
            parser.error("--transcribe 需要听谱入口和 --output 输出路径")
        try:
            from .converter.transcribe import transcribe
            transcribe(args.transcribe).save(args.output)
            return 0
        except Exception as e:
            error_path = Path(str(args.output)+".error.txt")
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(str(e),encoding="utf-8")
            return 1
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
    if args.page == "settings": backend.refreshAudioDevices()
    if args.demo: backend.loadDemo()
    if args.score: backend.loadProjectPath(args.score)
    engine = QQmlApplicationEngine()
    engine.quit.connect(app.quit)
    engine.rootContext().setContextProperty("bridge", backend)
    engine.rootContext().setContextProperty("initialPage", args.page)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "Main.qml")))
    if not engine.rootObjects():
        backend.close()
        return 1
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "CalibrationOverlay.qml")))
    if len(engine.rootObjects())<2:
        backend.close()
        return 1
    overlay = engine.rootObjects()[1]
    from .overlay import position_overlay
    placement = [None]
    def place_overlay():
        value = backend.calibration
        new = (value["visible"],value["monitor"],value["position"])
        if new != placement[0] and value["visible"]:
            position_overlay(overlay,value["monitor"],value["position"])
        placement[0] = new
    backend.calibrationChanged.connect(place_overlay)
    if args.overlay_demo: backend.previewCalibration()
    app.aboutToQuit.connect(backend.close)
    if args.screenshot:
        def capture():
            destination = Path(args.screenshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                ok = (overlay if args.overlay_demo else engine.rootObjects()[0]).grabWindow().save(str(destination))
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
