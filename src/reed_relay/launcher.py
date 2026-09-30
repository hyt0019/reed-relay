"""Report early frozen-runtime errors without hiding them in a windowed process."""
import os
from pathlib import Path
import sys
import traceback


def launch(mode):
    try:
        from .app import run
        return run(mode)
    except Exception:
        directory=Path(os.environ.get("REED_RELAY_DATA_DIR",str(Path(os.environ.get("APPDATA",str(Path.home())))/"ReedRelay")))
        directory.mkdir(parents=True,exist_ok=True)
        destination=directory/f"startup-{mode}.log"
        destination.write_text(traceback.format_exc(),encoding="utf-8")
        if sys.stderr: traceback.print_exc()
        if os.name=="nt" and not any(flag in sys.argv for flag in ("--screenshot","--transcribe")):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,f"启动失败，诊断记录已保存到：\n{destination}","ReedRelay",16)
        return 1
