from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
target = os.environ.get('REED_BUILD_TARGET', 'player')
name = 'ReedRelay-' + target.title()
datas = [(str(root/'src/reed_relay/ui'), 'reed_relay/ui'), (str(root/'docs/THIRD_PARTY.md'), '.')]
hidden = ['pyaudiowpatch']
excluded = ['tensorflow', 'torch', 'matplotlib', 'IPython', 'notebook', 'pytest', 'tkinter']
if target == 'player':
    excluded += ['reed_relay.converter', 'basic_pitch', 'librosa', 'scipy', 'sklearn', 'numba', 'llvmlite', 'onnxruntime', 'soundfile', 'imageio_ffmpeg', 'PySide6.QtMultimedia']
else:
    for module in ['basic_pitch', 'resampy', 'librosa', 'imageio_ffmpeg']:
        datas += collect_data_files(module)
    datas += copy_metadata('basic-pitch')
    hidden += ['onnxruntime', 'soundfile', 'resampy', 'librosa', 'pretty_midi', 'scipy.signal']
a = Analysis([str(root/'packaging'/f'{target}_entry.py')], pathex=[str(root/'src')],
             binaries=[], datas=datas, hiddenimports=hidden, hookspath=[],
             hooksconfig={}, runtime_hooks=[], excludes=excluded, noarchive=False,
             # Numba's cached functions need physical source paths in frozen apps.
             module_collection_mode={'librosa': 'py', 'resampy': 'py'})
# Qt's Windows build imports the OS ICU API (unsuffixed symbols). Build-machine
# PATH entries such as Poppler may expose an incompatible ICU with versioned
# exports. Never shadow the Windows ICU DLLs with those accidental dependencies.
a.binaries = [entry for entry in a.binaries if not (
    Path(entry[0]).name.lower() in {'icuuc.dll', 'icuin.dll'}
    or Path(entry[0]).name.lower().startswith('icudt'))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name, debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)
