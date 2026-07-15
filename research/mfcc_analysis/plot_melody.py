"""Melody-line extraction — vocal-only pyin f0 contour plotted on a note
scale, one PNG per band (3 songs side by side). Unlike the CQT panels
(which show the full spectral content of the vocal stem), this collapses
each frame down to a single monophonic pitch estimate, so it reads like a
melody transcription rather than a spectrogram.

Only works for tracks whose vocal stem already exists under stems/. Run
separate_vocals.py first for any band not yet processed.

Usage: python plot_melody.py mygo ave_mujica
"""
import os
import sys
import numpy as np
import pandas as pd
import librosa
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
_available = {f.name for f in font_manager.fontManager.ttflist}
for _cand in ("Yu Gothic", "MS Gothic", "Meiryo", "Malgun Gothic"):
    if _cand in _available:
        matplotlib.rcParams["font.family"] = _cand
        break
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(HERE, "selected_songs.csv")
STEMS_DIR = os.path.join(HERE, "stems", "htdemucs")
OUT_DIR = os.path.join(HERE, "fig", "melody")

SR = 22050
PYIN_FMIN = 80.0
PYIN_FMAX = 1000.0
NOTE_TICKS = ["C3", "E3", "G#3", "C4", "E4", "G#4", "C5", "E5", "G#5", "C6"]


def melody_contour(voc_path):
    y, sr = librosa.load(voc_path, sr=SR, mono=True)
    f0, voiced_flag, _ = librosa.pyin(y, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr)
    times = librosa.times_like(f0, sr=sr)
    f0_plot = np.where(voiced_flag, f0, np.nan)
    return times, f0_plot


def plot_band(band, rows, out_path):
    """rows: list of (song, voc_path), up to 3."""
    n = len(rows)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 3.2), squeeze=False, sharey=True)
    tick_hz = [librosa.note_to_hz(nn) for nn in NOTE_TICKS]
    for col, (song, voc_path) in enumerate(rows):
        times, f0 = melody_contour(voc_path)
        ax = axes[0, col]
        ax.plot(times, f0, lw=0.9, color="#c0392b")
        ax.set_yscale("log")
        ax.set_yticks(tick_hz)
        ax.set_yticklabels(NOTE_TICKS)
        ax.set_title(song, fontsize=9)
        ax.set_xlabel("time (s)")
        ax.grid(axis="y", alpha=0.3)
        if col == 0:
            ax.set_ylabel("melody pitch")

    fig.suptitle(f"{band}  —  vocal melody line (pyin)", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SEL_CSV)
    only_bands = sys.argv[1:]
    bands = sorted(df["band"].unique())
    if only_bands:
        bands = [b for b in bands if b in only_bands]
    for n, band in enumerate(bands, 1):
        sub = df[df["band"] == band].sort_values("idx")
        rows = []
        missing = []
        for r in sub.itertuples():
            voc_p = os.path.join(STEMS_DIR, r.tag, "vocals.wav")
            if os.path.isfile(voc_p):
                rows.append((r.song, voc_p))
            else:
                missing.append(r.tag)
        if missing:
            print(f"[{n}/{len(bands)}] {band}: MISSING vocal stems {missing}")
        if not rows:
            continue
        out_path = os.path.join(OUT_DIR, f"{band}_melody.png")
        print(f"[{n}/{len(bands)}] plotting {band} ({len(rows)} songs)", flush=True)
        plot_band(band, rows, out_path)
    print("[plot_melody] done")


if __name__ == "__main__":
    main()
