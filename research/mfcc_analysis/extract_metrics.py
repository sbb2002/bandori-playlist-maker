"""Step 4a — pull existing indicators + compute research-target vocal features
for the selected tracks. Adapts research/mood_warmth/extract_vocal_features.py.

Existing indicators (no recompute): from data/song_features_with_proxies.csv
  mode_score, energy_proxy, acousticness_proxy, instrumentalness_proxy,
  harmonic_ratio, contrast, rms, voiced_frac_mix, tempo_excerpt

Research-target indicators (recompute on demucs vocal stem, per
mood_warmth methodology): jitter_local, shimmer_local, hnr_mean,
f0_median_st, f0_range_st, f0_std_st, vocal_ratio, vocal_centroid
"""
import os
import numpy as np
import pandas as pd
import librosa
import parselmouth
from parselmouth.praat import call

HERE = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(HERE, "selected_songs.csv")
LOCAL_AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"
DL_AUDIO_DIR = os.path.join(HERE, "audio_dl")
STEMS_DIR = os.path.join(HERE, "stems", "htdemucs")
FEATURES_CSV = os.path.join(HERE, "..", "..", "data", "song_features_with_proxies.csv")
OUT_CSV = os.path.join(HERE, "combined_metrics.csv")

PITCH_FLOOR = 75.0
PITCH_CEILING = 1000.0
PYIN_FMIN = 80.0
PYIN_FMAX = 1000.0
SR_ANALYSIS = 22050

EXISTING_COLS = ["mode_score", "energy_proxy", "acousticness_proxy",
                  "instrumentalness_proxy", "harmonic_ratio", "contrast",
                  "rms", "voiced_frac_mix", "tempo_excerpt", "key"]


def mix_path(tag):
    local = os.path.join(LOCAL_AUDIO_DIR, tag + ".wav")
    if os.path.isfile(local):
        return local
    dl = os.path.join(DL_AUDIO_DIR, tag + ".wav")
    return dl if os.path.isfile(dl) else None


def hz_to_st(f0):
    return 69.0 + 12.0 * np.log2(f0 / 440.0)


def praat_features(y_mono, sr):
    snd = parselmouth.Sound(y_mono.astype(np.float64), sampling_frequency=float(sr))
    pp = call(snd, "To PointProcess (periodic, cc)", PITCH_FLOOR, PITCH_CEILING)
    jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    shimmer = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    harm = call(snd, "To Harmonicity (cc)", 0.01, PITCH_FLOOR, 0.1, 1.0)
    hnr = call(harm, "Get mean", 0, 0)
    return jitter, shimmer, hnr


def f0_features(y22, sr):
    f0, voiced_flag, _ = librosa.pyin(y22, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr)
    f0v = f0[np.isfinite(f0)]
    f0v = f0v[f0v > 0]
    if f0v.size < 5:
        return np.nan, np.nan, np.nan
    st = hz_to_st(f0v)
    return (float(np.median(st)),
            float(np.percentile(st, 95) - np.percentile(st, 5)),
            float(np.std(st, ddof=1)))


def rms(y):
    return float(np.sqrt(np.mean(np.square(y)))) if y.size else np.nan


def main():
    sel = pd.read_csv(SEL_CSV)
    feat = pd.read_csv(FEATURES_CSV)

    rows = []
    for n, r in enumerate(sel.itertuples(), 1):
        voc = os.path.join(STEMS_DIR, r.tag, "vocals.wav")
        mix = mix_path(r.tag)
        rec = {"band": r.band, "idx": r.idx, "song": r.song, "tag": r.tag}

        fr = feat[(feat["band"] == r.band) & (feat["idx"] == r.idx)]
        if len(fr) == 1:
            for c in EXISTING_COLS:
                rec[c] = fr.iloc[0][c]
        else:
            print(f"[{n}/{len(sel)}] {r.tag}: no existing-feature row (n={len(fr)})")
            for c in EXISTING_COLS:
                rec[c] = np.nan

        if mix is None or not os.path.isfile(voc):
            print(f"[{n}/{len(sel)}] {r.tag}: MISSING audio (mix={mix is not None} voc={os.path.isfile(voc)})")
            for c in ["jitter_local", "shimmer_local", "hnr_mean", "f0_median_st",
                      "f0_range_st", "f0_std_st", "vocal_ratio", "vocal_centroid"]:
                rec[c] = np.nan
            rows.append(rec)
            continue

        print(f"[{n}/{len(sel)}] {r.tag} vocal feature extraction", flush=True)
        try:
            yv, srv = librosa.load(voc, sr=None, mono=True)
            ym, srm = librosa.load(mix, sr=None, mono=True)

            jitter, shimmer, hnr = praat_features(yv, srv)
            yv22 = librosa.resample(yv, orig_sr=srv, target_sr=SR_ANALYSIS)
            med, rng, std = f0_features(yv22, SR_ANALYSIS)
            cent = float(np.mean(librosa.feature.spectral_centroid(y=yv22, sr=SR_ANALYSIS)))
            vr = rms(yv) / rms(ym)

            rec.update({
                "jitter_local": jitter, "shimmer_local": shimmer, "hnr_mean": hnr,
                "f0_median_st": med, "f0_range_st": rng, "f0_std_st": std,
                "vocal_ratio": vr, "vocal_centroid": cent,
            })
        except Exception as e:  # noqa
            print(f"    FAILED: {e!r}")
            for c in ["jitter_local", "shimmer_local", "hnr_mean", "f0_median_st",
                      "f0_range_st", "f0_std_st", "vocal_ratio", "vocal_centroid"]:
                rec[c] = np.nan
        rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[extract_metrics] wrote {OUT_CSV} ({len(out)} rows)")


if __name__ == "__main__":
    main()
