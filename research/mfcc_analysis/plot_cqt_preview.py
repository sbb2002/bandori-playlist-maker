"""Preview — CQT (musical-note scale) spectrogram for raw mix only, using
only the 21 songs whose audio is already cached locally (no download, no
Demucs). Used to validate the new axis/colormap before committing to the
full 30-song raw+vocal regeneration in plot_mfcc.py.
"""
import os
import numpy as np
import pandas as pd
import librosa
import librosa.display
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
LOCAL_AUDIO_DIR = r"C:\Users\User\Documents\pyworks\bandori-song-sorter\src\content\cluster\audio_full"
OUT_DIR = os.path.join(HERE, "fig", "cqt_preview")

SR = 22050
FMIN = librosa.note_to_hz("C2")
N_BINS = 72          # 6 octaves
BINS_PER_OCTAVE = 12


def compute_cqt_db(path):
    y, sr = librosa.load(path, sr=SR, mono=True)
    C = librosa.cqt(y, sr=sr, fmin=FMIN, n_bins=N_BINS, bins_per_octave=BINS_PER_OCTAVE)
    C_db = librosa.amplitude_to_db(np.abs(C), ref=np.max)
    return C_db, sr


def plot_band(band, rows, out_path):
    """rows: list of (song, mix_path), raw mix only."""
    n = len(rows)
    pairs = [(song, *compute_cqt_db(path)) for song, path in rows]

    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.4), squeeze=False)
    last_img = None
    for col, (song, C_db, sr) in enumerate(pairs):
        ax = axes[0, col]
        last_img = librosa.display.specshow(
            C_db, x_axis="time", y_axis="cqt_note", sr=sr,
            fmin=FMIN, bins_per_octave=BINS_PER_OCTAVE,
            ax=ax, cmap="magma", vmin=-60, vmax=0)
        ax.set_title(song, fontsize=9)
        ax.set_xlabel("time (s)")
        if col == 0:
            ax.set_ylabel("pitch (CQT)")
        else:
            ax.set_ylabel("")

    fig.suptitle(f"{band}  —  raw mix CQT (preview)", fontsize=12)
    fig.colorbar(last_img, ax=axes, format="%+2.0f dB", fraction=0.02)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SEL_CSV)
    df = df[df["has_local_audio"] == True]  # noqa: E712 — only locally cached songs
    bands = sorted(df["band"].unique())
    for n, band in enumerate(bands, 1):
        sub = df[df["band"] == band].sort_values("idx")
        rows = []
        for r in sub.itertuples():
            p = os.path.join(LOCAL_AUDIO_DIR, r.tag + ".wav")
            if os.path.isfile(p):
                rows.append((r.song, p))
        if not rows:
            continue
        out_path = os.path.join(OUT_DIR, f"{band}_cqt_preview.png")
        print(f"[{n}/{len(bands)}] plotting {band} ({len(rows)} songs)", flush=True)
        plot_band(band, rows, out_path)
    print("[plot_cqt_preview] done")


if __name__ == "__main__":
    main()
