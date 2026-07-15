"""Step 3 — plot raw-mix CQT vs vocal-only CQT, one PNG per band.

Layout per band: 2 rows x 3 cols. Row 0 = raw mix CQT, row 1 = vocal-only
CQT (demucs htdemucs). Columns = the band's 3 selected songs, so raw vs
vocal is compared vertically and songs are compared horizontally.

y-axis is a musical-note (pitch) scale via Constant-Q Transform, not MFCC
cepstral coefficients — MFCC's coefficient index has no frequency meaning,
so it can't be relabeled onto a note scale. Color is a sequential dB scale
(dark = quiet, bright = loud) instead of the old diverging coolwarm.

Optional CLI args restrict to specific bands, e.g. `python plot_mfcc.py
mygo ave_mujica` for a quick sample instead of the full 10-band run.
"""
import os
import sys
import numpy as np
import pandas as pd
import librosa
import librosa.display
import matplotlib
matplotlib.use("Agg")
# CJK 폰트 설정: 일본어 제목 렌더링 지원
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
DL_AUDIO_DIR = os.path.join(HERE, "audio_dl")
STEMS_DIR = os.path.join(HERE, "stems", "htdemucs")
OUT_DIR = os.path.join(HERE, "fig", "mfcc")

SR = 22050
FMIN = librosa.note_to_hz("C2")
N_BINS = 72          # 6 octaves
BINS_PER_OCTAVE = 12
DB_VMIN, DB_VMAX = -60, 0


def mix_path(tag):
    local = os.path.join(LOCAL_AUDIO_DIR, tag + ".wav")
    if os.path.isfile(local):
        return local
    dl = os.path.join(DL_AUDIO_DIR, tag + ".wav")
    return dl if os.path.isfile(dl) else None


def compute_cqt_db(path):
    y, sr = librosa.load(path, sr=SR, mono=True)
    C = librosa.cqt(y, sr=sr, fmin=FMIN, n_bins=N_BINS, bins_per_octave=BINS_PER_OCTAVE)
    C_db = librosa.amplitude_to_db(np.abs(C), ref=np.max)
    return C_db, sr


def plot_band(band, rows, out_path):
    """rows: list of (song, mix_p, voc_p) for this band, up to 3."""
    n = len(rows)
    pairs = []  # (cqt_raw_db, cqt_voc_db, sr, song)
    for song, mix_p, voc_p in rows:
        cqt_raw, sr = compute_cqt_db(mix_p)
        cqt_voc, _ = compute_cqt_db(voc_p)
        pairs.append((cqt_raw, cqt_voc, sr, song))

    fig, axes = plt.subplots(2, n, figsize=(4.2 * n, 6), squeeze=False, sharex="col")
    fig.subplots_adjust(hspace=0.0)
    last_img = None
    for col, (cqt_raw, cqt_voc, sr, song) in enumerate(pairs):
        last_img = librosa.display.specshow(
            cqt_raw, x_axis="time", y_axis="cqt_note", sr=sr,
            fmin=FMIN, bins_per_octave=BINS_PER_OCTAVE,
            ax=axes[0, col], cmap="magma", vmin=DB_VMIN, vmax=DB_VMAX)
        axes[0, col].set_title(song, fontsize=9)
        axes[0, col].set_xlabel("")
        axes[0, col].tick_params(labelbottom=False)
        if col == 0:
            axes[0, col].set_ylabel("raw mix\npitch (CQT)")
        else:
            axes[0, col].set_ylabel("")

        last_img = librosa.display.specshow(
            cqt_voc, x_axis="time", y_axis="cqt_note", sr=sr,
            fmin=FMIN, bins_per_octave=BINS_PER_OCTAVE,
            ax=axes[1, col], cmap="magma", vmin=DB_VMIN, vmax=DB_VMAX)
        axes[1, col].set_xlabel("time (s)")
        if col == 0:
            axes[1, col].set_ylabel("vocal-only\npitch (CQT)")
        else:
            axes[1, col].set_ylabel("")

    fig.suptitle(f"{band}  —  raw (top) vs vocal-only (bottom) CQT", fontsize=12)
    fig.colorbar(last_img, ax=axes, format="%+2.0f dB", fraction=0.02)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SEL_CSV)
    only_bands = sys.argv[1:]
    problems = []
    bands = sorted(df["band"].unique())
    if only_bands:
        bands = [b for b in bands if b in only_bands]
    for n, band in enumerate(bands, 1):
        out_path = os.path.join(OUT_DIR, f"{band}_mfcc.png")
        sub = df[df["band"] == band].sort_values("idx")
        rows = []
        missing = []
        for r in sub.itertuples():
            mix_p = mix_path(r.tag)
            voc_p = os.path.join(STEMS_DIR, r.tag, "vocals.wav")
            if mix_p is None or not os.path.isfile(voc_p):
                missing.append(r.tag)
                continue
            rows.append((r.song, mix_p, voc_p))
        if missing:
            print(f"[{n}/{len(bands)}] {band}: MISSING {missing}")
            problems.extend(missing)
        if not rows:
            continue
        print(f"[{n}/{len(bands)}] plotting {band} ({len(rows)} songs)", flush=True)
        try:
            plot_band(band, rows, out_path)
        except Exception as e:  # noqa
            print(f"    FAILED: {e!r}")
            problems.append(band)

    print(f"\n[plot_mfcc] {len(bands) - len([p for p in problems if p in bands])}/{len(bands)} band plots done")
    if problems:
        print("[plot_mfcc] problems:", problems)


if __name__ == "__main__":
    main()
