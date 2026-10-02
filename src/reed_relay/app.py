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
from PySide6.QtWidgets import QApplication, QFileDialog
from .backend import Backend


def run(mode):
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot")
    parser.add_argument("--binding-demo", action="store_true", help="显示按键捕获弹层供界面检查")
    parser.add_argument("--audition-demo", action="store_true", help="静音播放当前曲谱，用于检查实际音频管线")
    parser.add_argument("--page", default="main")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-hotkeys", action="store_true")
    parser.add_argument("--score")
    parser.add_argument("--transcribe")
    parser.add_argument('--import-scores', nargs='+', help='导入已有 MIDI/JSON 到配置的曲库，不启动界面；--output 可保存报告')
    parser.add_argument("--repair-score", help="修整已有曲谱碎音并另存，需 --output")
    parser.add_argument("--extract-score", help="从曲谱完整候选重新提取主旋律，需 --output")
    parser.add_argument("--minimum-pitch", type=int, default=0)
    parser.add_argument("--maximum-pitch", type=int, default=127)
    parser.add_argument("--short-note-ms", type=float, default=80.)
    parser.add_argument("--gap-ms", type=float, default=50.)
    parser.add_argument("--merge-repeats", action="store_true")
    parser.add_argument("--check-loopback", action="store_true", help="播放短参考音并验证电脑声音采集，需 --output")
    parser.add_argument("--output")
    parser.add_argument("--render-audition", help="从曲谱渲染口琴 WAV，不启动界面")
    parser.add_argument("--audition-mode", choices=["clean","game"], default="clean")
    parser.add_argument("--audition-speed", type=float, default=1.)
    args = parser.parse_args()
    repair_options = {'minimum_ms':args.short_note_ms,'gap_ms':args.gap_ms,'merge_repeats':args.merge_repeats}
    melody_options = {'minimum_pitch':args.minimum_pitch, 'maximum_pitch':args.maximum_pitch}
    if args.import_scores:
        import json
        from .storage import Storage
        from .core.score import atomic_json
        from .library import ScoreLibrary, default_library
        storage = Storage()
        preference_file = storage.directory/'preferences.json'
        preferences = json.loads(preference_file.read_text(encoding='utf-8')) if preference_file.exists() else {}
        library = ScoreLibrary(preferences.get('library_directory') or default_library(storage.directory))
        imported, failures = [], []
        for path in args.import_scores:
            try:
                result = library.import_score(path)
                imported.append({'source':path, 'path':str(result.path), 'created':result.created})
            except Exception as error: failures.append({'source':path, 'error':str(error)})
        report = {'directory':str(library.directory), 'imported':imported, 'failures':failures, 'entries':library.scan()}
        if args.output: atomic_json(args.output, report)
        else: print(json.dumps(report, ensure_ascii=False))
        return 1 if failures else 0
    if args.extract_score:
        if not args.output: parser.error('--extract-score 需要 --output')
        from .core.score import Score
        from .core.melody import select_melody, repair_melody, model_semitone_notes
        score = Score.load(args.extract_score)
        if not score.original_notes: score.original_notes = list(score.notes)
        candidates = model_semitone_notes(score.original_notes, score.metadata)
        score.notes = repair_melody(select_melody(candidates, **melody_options), **repair_options)
        if not score.notes: raise ValueError('当前音域和碎音阈值下没有旋律候选')
        score.save(args.output)
        return 0
    if args.repair_score:
        if not args.output: parser.error("--repair-score 需要 --output")
        from .core.score import Score
        from .core.melody import repair_melody
        score = Score.load(args.repair_score)
        if not score.original_notes: score.original_notes = list(score.notes)
        score.notes = repair_melody(score.notes, **repair_options)
        if not score.notes: raise ValueError('修整后没有音符，请降低 --short-note-ms')
        score.save(args.output)
        return 0
    if args.render_audition:
        if not args.output: parser.error("--render-audition 需要 --output")
        from .core.score import Score
        from .core.harmonica import synthesize_harmonica
        score=Score.load(args.render_audition)
        synthesize_harmonica(score,args.output,speed=args.audition_speed,mode=args.audition_mode)
        return 0
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
            transcribe(args.transcribe, **repair_options, **melody_options).save(args.output)
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
    from .storage import Storage, application_root
    task_root = application_root()
    if not args.screenshot and not os.environ.get('REED_RELAY_DATA_DIR') and not (task_root/'storage-location.json').exists() and task_root.drive.upper() == 'C:':
        path = QFileDialog.getExistingDirectory(None, '选择数据保存目录（程序位于 C 盘，请先选择作品保存位置）', str(task_root))
        if not path: return 0
        Storage(initial_directory=Path(path))
    backend = Backend(mode, no_hotkeys=args.no_hotkeys or bool(args.screenshot))
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
    if args.binding_demo:
        QTimer.singleShot(250,lambda:backend.beginBinding("note:0","音符 1"))
    if args.audition_demo:
        backend.audition.setVolume(0)
        QTimer.singleShot(100,backend.auditionScore)
    app.aboutToQuit.connect(backend.close)
    if args.screenshot:
        def capture():
            destination = Path(args.screenshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not engine.rootObjects()[0].property("pagesReady"):
                    app.exit(3); return
                if args.audition_demo and (not backend.audition.playing or backend.audition.position <= 0):
                    app.exit(4); return
                ok = engine.rootObjects()[0].grabWindow().save(str(destination))
                app.exit(0 if ok else 2)
            except Exception:
                app.exit(2)
        QTimer.singleShot(2500 if args.audition_demo else 1200, capture)
    return app.exec()


def player_main(): return run("player")
def converter_main(): return run("converter")


if __name__ == "__main__":
    mode = "converter" if "--converter" in sys.argv else "player"
    if "--converter" in sys.argv: sys.argv.remove("--converter")
    sys.exit(run(mode))
