"""Quick exploratory chord-progression estimate — chroma + major/minor
triad template matching, median-filtered and collapsed into segments.

This is NOT a proper chord recognition model (no madmom/deep model
available in this env) — just a coarse heuristic to sanity-check whether
two songs' harmonic movement looks different. Expect errors on distorted
guitar / complex voicings.
"""
import sys
import numpy as np
import librosa
from scipy.ndimage import median_filter

SR = 22050
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def build_templates():
    templates = []
    labels = []
    for root in range(12):
        maj = np.zeros(12); maj[[root, (root + 4) % 12, (root + 7) % 12]] = 1
        minr = np.zeros(12); minr[[root, (root + 3) % 12, (root + 7) % 12]] = 1
        templates.append(maj); labels.append(f"{NOTE_NAMES[root]}")
        templates.append(minr); labels.append(f"{NOTE_NAMES[root]}m")
    return np.array(templates), labels


def estimate(path, hop=4096):
    y, sr = librosa.load(path, sr=SR, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    templates, labels = build_templates()
    norm_chroma = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
    norm_templates = templates / np.linalg.norm(templates, axis=1, keepdims=True)
    sims = norm_templates @ norm_chroma  # (24, n_frames)
    frame_idx = np.argmax(sims, axis=0)
    frame_idx = median_filter(frame_idx, size=9)
    times = librosa.frames_to_time(np.arange(len(frame_idx)), sr=sr, hop_length=hop)

    segments = []
    cur, start = frame_idx[0], times[0]
    for i in range(1, len(frame_idx)):
        if frame_idx[i] != cur:
            segments.append((start, times[i], labels[cur]))
            cur, start = frame_idx[i], times[i]
    segments.append((start, times[-1], labels[cur]))
    return segments


if __name__ == "__main__":
    path, name = sys.argv[1], sys.argv[2]
    segs = estimate(path)
    print(f"--- {name} ---")
    for s, e, lab in segs:
        if e - s < 1.5:  # drop very short blips from the printout
            continue
        print(f"{s:6.1f}-{e:6.1f}s  {lab}")
