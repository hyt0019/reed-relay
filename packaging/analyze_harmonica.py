"""Extract a small additive sound model; private recordings never enter the repo.

Usage: python packaging/analyze_harmonica.py <recordings directory> <model.json>
Only explicitly reviewed takes are read. 正常1's third take is excluded by design.
Requires the converter's soundfile/scipy dependencies only at authoring time.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


TAKES = {
    "normal_c": ("正常1.wav", 60, 260.65, [5.00, 14.34]),
    "normal_d": ("正常2.wav", 62, 294.05, [4.49, 14.15, 22.61]),
    "lower": ("降调1.wav", 48, 131.76, [5.13, 14.78, 23.91]),
    "upper": ("升调1.wav", 72, 529.53, [5.13, 14.09, 23.09]),
    "sharp": ("半音1.wav", 61, 278.3, [13.79, 21.54]),
}
TIMES = [0, .04, .08, .12, .2, .35, .55, .8, 1.2, 1.8, 2.4, 2.8,
         3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.3, 4.6, 5.0, 5.3, 5.6]


def extract(directory):
    models = []
    for name, (file, pitch, root, starts) in TAKES.items():
        audio, sr = sf.read(directory / file, always_2d=True)
        if sr != 48000:
            raise ValueError(f"Expected the reviewed 48 kHz source: {file}")
        channel = int(np.argmax(np.mean(audio * audio, axis=0)))
        audio = resample_poly(audio[:, channel], 1, 2)
        sr = 24000
        observations, frequencies = [], []
        for start in starts:
            amps, hz = [], []
            for t in TIMES:
                pos = max(0, int((start + t - .032) * sr))
                frame = audio[pos:pos + 3072]
                if len(frame) != 3072:
                    raise ValueError(f"Reviewed take incomplete: {file} at {start}")
                window = np.hanning(len(frame))
                spectrum = abs(np.fft.rfft((frame-frame.mean()) * window, 65536))
                freq = np.fft.rfftfreq(65536, 1/sr)
                candidates = []
                for h in range(1, 11):
                    lo, hi = np.searchsorted(freq, [root*h*.975, root*h*1.025])
                    k = lo + int(np.argmax(spectrum[lo:hi]))
                    if k in (lo, hi-1):
                        continue
                    a, b, c = np.log(np.maximum(spectrum[k-1:k+2], 1e-15))
                    delta = .5*(a-c)/(a-2*b+c)
                    candidates.append((spectrum[k], (k+delta)*sr/65536/h))
                candidates.sort(reverse=True)
                fundamental = float(np.median([c[1] for c in candidates[:5]])) if candidates else root
                fundamental = float(np.clip(fundamental, root*.975, root*1.025))
                magnitudes = []
                for h in range(1, 33):
                    center = fundamental*h
                    if center > sr*.46:
                        magnitudes.append(0.)
                        continue
                    lo, hi = np.searchsorted(freq, [center-8, center+8])
                    magnitudes.append(float(np.max(spectrum[lo:hi])*2/window.sum()))
                amps.append(magnitudes)
                hz.append(fundamental)
            observations.append(amps)
            frequencies.append(hz)
        amplitude = np.median(observations, axis=0)
        # Low-level incoherent energy is predominantly the recording's background.
        amplitude[amplitude < max(float(amplitude.max())*.008, .00012)] = 0
        cents = 1200*np.log2(np.median(frequencies, axis=0)/(440*2**((pitch-69)/12)))
        models.append({"id": name, "root_pitch": pitch, "source": file,
                       "takes_used": len(starts), "times": TIMES,
                       "harmonics": np.round(amplitude, 7).tolist(),
                       "cents": np.round(cents, 2).tolist()})
    return {"schema_version": 1, "name": "游戏口琴 · 录音参数模型",
            "method": "Median harmonic envelopes from reviewed takes; adjacent pitches inferred",
            "excluded": "正常1.wav take 3; sharp take 1 omitted in favor of cleaner repeats",
            "models": models}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(extract(args.directory), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {args.output}; no source audio copied")
