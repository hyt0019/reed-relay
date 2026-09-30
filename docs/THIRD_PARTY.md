# Third-party components

ReedRelay uses these projects through their published packages. The project itself has not yet selected an open-source license; dependencies retain their own licenses.

| Component | Purpose | Upstream |
|---|---|---|
| PySide6 / Qt | Desktop UI and audio preview | https://doc.qt.io/qtforpython-6/licenses.html |
| NumPy | Signal analysis and synthesis | https://numpy.org/doc/stable/license.html |
| SoundDevice / PortAudio | Microphone and reference tone | https://github.com/spatialaudio/python-sounddevice |
| Mido | MIDI import/export | https://github.com/mido/mido |
| Basic Pitch 0.4.0 | Audio-to-note model and post-processing (Apache-2.0) | https://github.com/spotify/basic-pitch |
| ONNX Runtime | Local model inference | https://github.com/microsoft/onnxruntime |
| Librosa / SciPy / Resampy / PrettyMIDI | Audio and transcription support | https://librosa.org/ / https://scipy.org/ / https://github.com/bmcfee/resampy / https://github.com/craffel/pretty-midi |
| SoundFile / libsndfile | Audio decoding | https://github.com/bastibe/python-soundfile |
| ImageIO-FFmpeg / FFmpeg | Fallback decoder for formats such as M4A | https://github.com/imageio/imageio-ffmpeg / https://ffmpeg.org/legal.html |

Basic Pitch is installed with `--no-deps` because its 0.4.0 wheel declares TensorFlow for Python 3.11+, even though it also supports ONNX. All used runtime dependencies are explicitly declared in the converter extra. Resampy 0.4.2 requires `pkg_resources`; setuptools is pinned below 81 for compatibility. Missing TensorFlow/CoreML/TFLite warnings are expected in an ONNX-only installation.

Before redistributing portable binaries, retain the applicable dependency notices and satisfy the licenses for the exact Qt/FFmpeg builds bundled. Current builds are provided locally for validation; no binary GitHub Release has been published.
