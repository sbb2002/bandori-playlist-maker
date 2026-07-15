"""Step 3 — plot raw-mix MFCC vs vocal-only MFCC, one PNG per band.

Layout per band: 2 rows x 3 cols. Row 0 = raw mix MFCC, row 1 = vocal-only
MFCC (demucs htdemucs). Columns = the band's 3 selected songs, so raw vs
vocal is compared vertically and songs are compared horizontally.
"""
import os
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
LOCAL_AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"
DL_AUDIO_DIR = os.path.join(HERE, "audio_dl")
STEMS_DIR = os.path.join(HERE, "stems", "htdemucs")
OUT_DIR = os.path.join(HERE, "fig", "mfcc")

N_MFCC = 20
SR = 22050


def mix_path(tag):
    local = os.path.join(LOCAL_AUDIO_DIR, tag + ".wav")
    if os.path.isfile(local):
        return local
    dl = os.path.join(DL_AUDIO_DIR, tag + ".wav")
    return dl if os.path.isfile(dl) else None


def compute_mfcc(path):
    y, sr = librosa.load(path, sr=SR, mono=True)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    return mfcc, sr


def plot_band(band, rows, out_path):
    """rows: list of (song, mix_p, voc_p) for this band, up to 3."""
    n = len(rows)
    pairs = []  # (mfcc_raw, mfcc_voc, sr, song)
    for song, mix_p, voc_p in rows:
        mfcc_raw, sr = compute_mfcc(mix_p)
        mfcc_voc, _ = compute_mfcc(voc_p)
        pairs.append((mfcc_raw[1:], mfcc_voc[1:], sr, song))

    _allvals = np.concatenate([np.abs(mr).ravel() for mr, mv, _, _ in pairs]
                              + [np.abs(mv).ravel() for mr, mv, _, _ in pairs])
    vmax = float(np.percentile(_allvals, 98))
    vmin = -vmax

    fig, axes = plt.subplots(2, n, figsize=(4.2 * n, 6), squeeze=False, sharex="col")
    fig.subplots_adjust(hspace=0.0)
    last_img = None
    for col, (mfcc_raw, mfcc_voc, sr, song) in enumerate(pairs):
        last_img = librosa.display.specshow(
            mfcc_raw, x_axis="time", sr=sr, ax=axes[0, col],
            cmap="coolwarm", vmin=vmin, vmax=vmax)
        axes[0, col].set_title(song, fontsize=9)
        axes[0, col].set_xlabel("")
        axes[0, col].tick_params(labelbottom=False)
        if col == 0:
            axes[0, col].set_ylabel("raw mix\nMFCC 1–19")

        last_img = librosa.display.specshow(
            mfcc_voc, x_axis="time", sr=sr, ax=axes[1, col],
            cmap="coolwarm", vmin=vmin, vmax=vmax)
        axes[1, col].set_xlabel("time (s)")
        if col == 0:
            axes[1, col].set_ylabel("vocal-only\nMFCC 1–19")

    fig.suptitle(f"{band}  —  raw (top) vs vocal-only (bottom) MFCC", fontsize=12)
    fig.colorbar(last_img, ax=axes, format="%+2.0f", fraction=0.02)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SEL_CSV)
    problems = []
    bands = sorted(df["band"].unique())
    for n, band in enumerate(bands, 1):
        out_path = os.path.join(OUT_DIR, f"{band}_mfcc.png")
        if os.path.isfile(out_path):
            print(f"[{n}/{len(bands)}] skip {band} (already plotted)")
            continue
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
