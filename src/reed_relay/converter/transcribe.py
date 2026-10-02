from __future__ import annotations

from pathlib import Path
import threading
import numpy as np
from reed_relay.core.score import Note, Score
from reed_relay.core.melody import repair_melody, select_melody
from .audio import decode, waveform_peaks, check_cancel


def transcribe(path, melody=True, cancel=None, progress=lambda *args: None, *, minimum_ms=80., gap_ms=50., merge_repeats=False,
               minimum_pitch=0, maximum_pitch=127):
    cancel = cancel or threading.Event()
    path = Path(path)
    progress(.01, "正在解码音频", None)
    audio, rate = decode(path, cancel)
    duration_ms = len(audio) / rate * 1000
    progress(.06, "加载音符识别模型（首次启动可能稍慢）", {"waveform": waveform_peaks(audio), "duration_ms": duration_ms})
    import basic_pitch
    from basic_pitch.inference import Model, window_audio_file
    from basic_pitch.constants import AUDIO_N_SAMPLES, FFT_HOP
    from basic_pitch.note_creation import output_to_notes_polyphonic, get_pitch_bends
    model_file = Path(basic_pitch.__file__).parent / "saved_models/icassp_2022/nmp.onnx"
    if not model_file.exists():
        raise RuntimeError("缺少 Basic Pitch ONNX 模型，请运行 setup.ps1 -Module all")
    model = Model(model_file)
    overlap_frames = 30
    overlap_samples = overlap_frames * FFT_HOP
    hop = AUDIO_N_SAMPLES - overlap_samples
    padded = np.concatenate((np.zeros(overlap_samples // 2, dtype=np.float32), audio))
    count = max(1, int(np.ceil(len(padded) / hop)))
    output = {"note": [], "onset": [], "contour": []}
    for i, (window, _) in enumerate(window_audio_file(padded, hop)):
        check_cancel(cancel)
        prediction = model.predict(window[None, ...].astype(np.float32))
        for key in output:
            output[key].append(prediction[key])
        progress(.1 + .75*(i+1)/count, f"识别音符 {i+1}/{count}", None)
    check_cancel(cancel)
    unwrapped, times = unwrap_with_times(output, hop, FFT_HOP, rate, duration_ms/1000, overlap_frames//2)
    progress(.87, "整理完整音符与原始时间", None)
    frame_notes = output_to_notes_polyphonic(unwrapped["note"], unwrapped["onset"], onset_thresh=.5,
                                             frame_thresh=.3, min_note_len=8, infer_onsets=True,
                                             max_freq=None, min_freq=None, melodia_trick=True)
    candidates = get_pitch_bends(unwrapped["contour"], frame_notes)
    check_cancel(cancel)
    notes, bends = [], {}
    for start, end, pitch, activation, bend in candidates:
        start_ms = max(0., float(times[start])*1000)
        end_ms = min(duration_ms, float(times[min(end, len(times)-1)])*1000)
        if end_ms <= start_ms: continue
        note = Note(round(start_ms, 3), round(end_ms-start_ms, 3), int(pitch),
                    max(1, min(127, round(float(activation)*127))),
                    max(0., min(1., float(activation))))
        notes.append(note)
        if bend: bends[note.id] = [int(v) for v in bend]
    notes.sort(key=lambda n: (n.start_ms, n.midi_pitch))
    progress(.95, "生成可校对曲谱", None)
    draft = repair_melody(select_melody(notes, minimum_pitch=minimum_pitch, maximum_pitch=maximum_pitch),
                          minimum_ms, gap_ms, merge_repeats) if melody else list(notes)
    score = Score(path.stem, draft, duration_ms,
                  source_file=str(path.resolve()), original_notes=list(notes),
                  metadata={"engine": "Spotify Basic Pitch 0.4.0 / ONNX", "mode": "melody" if melody else "all-notes",
                            "waveform": waveform_peaks(audio),
                            "bpm_estimated": False, "confidence_kind": "model activation, not calibrated probability",
                            "pitch_policy": "midi-semitones; uncalibrated contour retained only as metadata",
                            "melody_selection": {"algorithm":"register-path-v2", "minimum_pitch":minimum_pitch,
                                                 "maximum_pitch":maximum_pitch} if melody else None,
                            "melody_repair": {"minimum_ms":minimum_ms,"gap_ms":gap_ms,"merge_repeats":merge_repeats} if melody else None,
                            "pitch_bends_third_semitone": bends,
                            "notice": "原始候选完整保留；主旋律为可编辑的自动简化，混音歌曲需要试听校对。"})
    score.validate()
    progress(1., f"完成：{len(score.notes)} 个音符，原始候选 {len(notes)} 个", None)
    return score


def unwrap_with_times(output, window_hop, frame_hop, rate, duration, crop):
    """Map retained frames to their source windows; do not accumulate hop rounding."""
    blocks = {key: np.concatenate(value)[:, crop:-crop, :] for key, value in output.items()}
    windows, frames = blocks["note"].shape[:2]
    # Leading waveform padding cancels the cropped leading model frames.
    times = (np.arange(windows)[:, None]*window_hop + np.arange(frames)[None, :]*frame_hop).reshape(-1)/rate
    valid = times < duration
    result = {key: block.reshape(-1, block.shape[-1])[valid] for key, block in blocks.items()}
    return result, np.concatenate((times[valid], [duration]))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert audio without launching the GUI")
    parser.add_argument("audio")
    parser.add_argument("output")
    parser.add_argument("--all-notes", action="store_true")
    parser.add_argument("--short-note-ms", type=float, default=80.)
    parser.add_argument("--gap-ms", type=float, default=50.)
    parser.add_argument("--merge-repeats", action="store_true")
    parser.add_argument("--minimum-pitch", type=int, default=0)
    parser.add_argument("--maximum-pitch", type=int, default=127)
    args = parser.parse_args()
    score = transcribe(args.audio, melody=not args.all_notes, minimum_ms=args.short_note_ms,
                       gap_ms=args.gap_ms, merge_repeats=args.merge_repeats,
                       minimum_pitch=args.minimum_pitch, maximum_pitch=args.maximum_pitch,
                       progress=lambda p,s,_: print(f"{p:.0%} {s}", flush=True))
    score.save(args.output)
    print(f"Saved {len(score.notes)} notes; duration {score.duration_ms/1000:.2f}s")


if __name__ == "__main__": main()
