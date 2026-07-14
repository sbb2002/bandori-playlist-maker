"""Step 2 — Vocal phonation feature extraction.

For each of 32 tracks (29 labeled + 3 anchors), from the FULL demucs vocal stem
(not an excerpt) plus the original mix, extract 8 features:
  Praat (parselmouth): jitter_local, shimmer_local, hnr_mean (dB)
  librosa pyin (semitones): f0_median_st, f0_range_st (p95-p5), f0_std_st
  vocal_ratio  = RMS(vocal stem) / RMS(original mix)
  vocal_centroid = mean spectral centroid of vocal stem (Hz)

Deterministic (no RNG). Output: research/mood_warmth/vocal_features.csv (32 rows).
"""
import io
import os
import sys

import numpy as np
import pandas as pd
import librosa
import parselmouth
from parselmouth.praat import call

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = r"C:\Users\User\Documents\pyworks\bandori-song-sorter\src\content\cluster\audio_full"
WORKSHEET = os.path.join(HERE, "candidates_worksheet.csv")
STEMS_DIR = os.path.join(HERE, "stems")
MODEL = "htdemucs"
OUT_CSV = os.path.join(HERE, "vocal_features.csv")

PITCH_FLOOR = 75.0
PITCH_CEILING = 1000.0
PYIN_FMIN = 80.0
PYIN_FMAX = 1000.0
SR_ANALYSIS = 22050

ANCHORS = [
    ("morfonica", 208, "esora no clover"),
    ("morfonica", 196, "Sonorous"),
    ("ave_mujica", 78, "天球のMúsica"),
]


def track_name(band, idx):
    return f"{band}__{idx:03d}"


def hz_to_st(f0):
    return 69.0 + 12.0 * np.log2(f0 / 440.0)


def build_targets():
    df = pd.read_csv(WORKSHEET)
    df = df[df["similarity_rating_1to5"].astype(str).str.strip() != "-"]
    labeled = [(str(b), int(i), str(s)) for b, i, s in
               zip(df["band"], df["idx"], df["song"])]
    out, seen = [], set()
    for b, i, s in labeled + ANCHORS:
        if (b, i) not in seen:
            seen.add((b, i))
            out.append((b, i, s))
    return out


def praat_features(y_mono, sr):
    """jitter_local, shimmer_local, hnr_mean via Praat standard procedure."""
    snd = parselmouth.Sound(y_mono.astype(np.float64), sampling_frequency=float(sr))
    pp = call(snd, "To PointProcess (periodic, cc)", PITCH_FLOOR, PITCH_CEILING)
    jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    shimmer = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    harm = call(snd, "To Harmonicity (cc)", 0.01, PITCH_FLOOR, 0.1, 1.0)
    hnr = call(harm, "Get mean", 0, 0)
    return jitter, shimmer, hnr


def f0_features(y22, sr):
    f0, voiced_flag, _ = librosa.pyin(
        y22, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr)
    f0v = f0[np.isfinite(f0)]
    f0v = f0v[f0v > 0]
    if f0v.size < 5:
        return np.nan, np.nan, np.nan, int(f0v.size)
    st = hz_to_st(f0v)
    med = float(np.median(st))
    rng = float(np.percentile(st, 95) - np.percentile(st, 5))
    std = float(np.std(st, ddof=1))
    return med, rng, std, int(f0v.size)


def rms(y):
    return float(np.sqrt(np.mean(np.square(y)))) if y.size else np.nan


COLS = ["band", "idx", "song", "jitter_local", "shimmer_local", "hnr_mean",
        "f0_median_st", "f0_range_st", "f0_std_st", "vocal_ratio",
        "vocal_centroid", "n_voiced_frames"]


def main():
    targets = build_targets()
    print(f"[extract] {len(targets)} tracks")

    # Resume support: rows are appended to OUT_CSV per track; already-extracted
    # tracks are skipped so the script is safe to re-run after a timeout.
    done_keys = set()
    if os.path.isfile(OUT_CSV):
        prev = pd.read_csv(OUT_CSV)
        done_keys = {(str(b), int(i)) for b, i in zip(prev["band"], prev["idx"])}
        print(f"[extract] resuming — {len(done_keys)} tracks already extracted")
    else:
        pd.DataFrame(columns=COLS).to_csv(OUT_CSV, index=False, encoding="utf-8")

    problems = []
    for n, (band, idx, song) in enumerate(targets, 1):
        tag = track_name(band, idx)
        if (band, idx) in done_keys:
            print(f"[{n}/{len(targets)}] skip {tag} (already extracted)", flush=True)
            continue
        voc = os.path.join(STEMS_DIR, MODEL, tag, "vocals.wav")
        mix = os.path.join(AUDIO_DIR, tag + ".wav")
        print(f"[{n}/{len(targets)}] {tag}", flush=True)
        rec = {"band": band, "idx": idx, "song": song}
        try:
            yv, srv = librosa.load(voc, sr=None, mono=True)
            ym, srm = librosa.load(mix, sr=None, mono=True)

            jitter, shimmer, hnr = praat_features(yv, srv)

            yv22 = librosa.resample(yv, orig_sr=srv, target_sr=SR_ANALYSIS)
            med, rng, std, nvoiced = f0_features(yv22, SR_ANALYSIS)

            cent = float(np.mean(librosa.feature.spectral_centroid(
                y=yv22, sr=SR_ANALYSIS)))

            vr = rms(yv) / rms(ym)

            rec.update({
                "jitter_local": jitter,
                "shimmer_local": shimmer,
                "hnr_mean": hnr,
                "f0_median_st": med,
                "f0_range_st": rng,
                "f0_std_st": std,
                "vocal_ratio": vr,
                "vocal_centroid": cent,
                "n_voiced_frames": nvoiced,
            })
            # flag any NaN
            for k, v in rec.items():
                if isinstance(v, float) and not np.isfinite(v):
                    problems.append(f"{tag}: {k} is NaN/inf")
        except Exception as e:  # noqa
            problems.append(f"{tag}: EXCEPTION {e!r}")
            for k in COLS[3:]:
                rec.setdefault(k, np.nan)
        # append this track's row immediately (resume-safe)
        pd.DataFrame([rec])[COLS].to_csv(
            OUT_CSV, mode="a", header=False, index=False, encoding="utf-8")

    final = pd.read_csv(OUT_CSV)
    print(f"\n[extract] {OUT_CSV} now has {len(final)} rows "
          f"(target {len(targets)})")
    nan_cells = final[COLS[3:]].isna().sum().sum()
    if problems:
        print("[extract] PROBLEMS this run:")
        for p in problems:
            print("  ", p)
    print(f"[extract] NaN cells in feature columns: {nan_cells}")
    return 0 if (len(final) == len(targets) and not problems) else 1


if __name__ == "__main__":
    sys.exit(main())
