"""Round 2 — Vocal phonation feature extraction for the FULL 661-song catalog.

Reuses the phonation logic from extract_vocal_features.py (Praat jitter/shimmer/hnr,
pyin f0_median/range/std, vocal_centroid), with three changes for the full run
(ROUND2-valence-proxy-DESIGN.md):

  1. Input: demucs vocal stems at
     topic/vector-embedding/src/method-1/work/stems_full/htdemucs/<tag>/vocals.wav
     (tag = {band}__{idx:03d}). Target list from full_catalog_songs.csv (661).
  2. NO mix-dependent feature: vocal_ratio is dropped (original mixes only partially
     present) — librosa.load(mix) is removed entirely. vocals.wav-only features:
       Praat  : jitter_local, shimmer_local, hnr_mean (dB)
       pyin   : f0_median_st, f0_range_st (p95-p5), f0_std_st  (semitones)
       librosa: vocal_centroid (Hz), n_voiced_frames
  3. Parallel: ~26s/track (pyin-dominated) x 661 ≈ 5h single-threaded, so extraction
     is parallelized with joblib.Parallel(n_jobs=-1, backend="loky"). The worker
     (extract_one) is a module top-level function and runs only under __main__.

pyin (PYIN_FMIN/FMAX) and Praat parameters are IDENTICAL to the reference script so
the resulting values stay consistent with round-1 c3 (do not change them).

Resume-safe: rows are appended to the output CSV in batches; on restart, tags already
present are skipped. Progress is mirrored to out/round2_extract_progress.json.

Deterministic (no RNG). Output: mood_warmth/vocal_features_full.csv (661 rows target).

Usage:
  # 5-track smoke test (writes vocal_features_smoke.csv, does not touch the full CSV):
  python extract_vocal_features_full.py --smoke 5
  # full run:
  python extract_vocal_features_full.py
"""
import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

# NOTE: librosa / parselmouth are imported INSIDE the worker functions, not at module
# top level. This script runs as __main__, so joblib's loky backend pickles the worker
# by value (cloudpickle) and would otherwise drag in module-global parselmouth handles,
# which contain unpicklable PyCapsule objects ("cannot pickle 'PyCapsule' object").
# Local imports keep the pickled global namespace clean; each worker process imports
# these libraries independently, exactly as intended.

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
STEMS_DIR = os.path.join(
    _REPO_ROOT, "topic", "vector-embedding", "src", "method-1",
    "work", "stems_full", "htdemucs",
)
CATALOG_CSV = os.path.join(
    _REPO_ROOT, "topic", "vector-embedding", "src", "method-1", "full_catalog_songs.csv",
)
OUT_CSV = os.path.join(HERE, "vocal_features_full.csv")
SMOKE_CSV = os.path.join(HERE, "vocal_features_smoke.csv")
OUT_DIR = os.path.join(HERE, "out")
PROGRESS_PATH = os.path.join(OUT_DIR, "round2_extract_progress.json")

# --- Praat / pyin parameters: MUST match extract_vocal_features.py (round-1 parity) ---
PITCH_FLOOR = 75.0
PITCH_CEILING = 1000.0
PYIN_FMIN = 80.0
PYIN_FMAX = 1000.0
SR_ANALYSIS = 22050

BATCH_SIZE = 40  # per-batch append cadence (resume granularity)

# vocal_ratio dropped vs reference; tag added as join key.
COLS = ["tag", "band", "idx", "song", "jitter_local", "shimmer_local", "hnr_mean",
        "f0_median_st", "f0_range_st", "f0_std_st", "vocal_centroid",
        "n_voiced_frames"]
FEATURE_COLS = COLS[4:]


def hz_to_st(f0):
    return 69.0 + 12.0 * np.log2(f0 / 440.0)


def praat_features(y_mono, sr):
    """jitter_local, shimmer_local, hnr_mean via the Praat standard procedure.

    Parameters identical to extract_vocal_features.py.
    """
    import parselmouth
    from parselmouth.praat import call

    snd = parselmouth.Sound(y_mono.astype(np.float64), sampling_frequency=float(sr))
    pp = call(snd, "To PointProcess (periodic, cc)", PITCH_FLOOR, PITCH_CEILING)
    jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    shimmer = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    harm = call(snd, "To Harmonicity (cc)", 0.01, PITCH_FLOOR, 0.1, 1.0)
    hnr = call(harm, "Get mean", 0, 0)
    return jitter, shimmer, hnr


def f0_features(y22, sr):
    """pyin f0 in semitones: median, range (p95-p5), std, n_voiced_frames."""
    import librosa

    f0, voiced_flag, _ = librosa.pyin(y22, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr)
    f0v = f0[np.isfinite(f0)]
    f0v = f0v[f0v > 0]
    if f0v.size < 5:
        return np.nan, np.nan, np.nan, int(f0v.size)
    st = hz_to_st(f0v)
    med = float(np.median(st))
    rng = float(np.percentile(st, 95) - np.percentile(st, 5))
    std = float(np.std(st, ddof=1))
    return med, rng, std, int(f0v.size)


def extract_one(task):
    """Worker: extract vocals.wav-only phonation features for one track.

    Top-level (picklable) so joblib's loky backend can ship it to worker processes.
    Each process imports librosa/parselmouth independently; no shared state.
    """
    import librosa

    tag, band, idx, song = task
    voc = os.path.join(STEMS_DIR, tag, "vocals.wav")
    rec = {"tag": tag, "band": band, "idx": idx, "song": song, "error": ""}
    try:
        yv, srv = librosa.load(voc, sr=None, mono=True)

        jitter, shimmer, hnr = praat_features(yv, srv)

        yv22 = librosa.resample(yv, orig_sr=srv, target_sr=SR_ANALYSIS)
        med, rng, std, nvoiced = f0_features(yv22, SR_ANALYSIS)

        cent = float(np.mean(librosa.feature.spectral_centroid(y=yv22, sr=SR_ANALYSIS)))

        rec.update({
            "jitter_local": jitter,
            "shimmer_local": shimmer,
            "hnr_mean": hnr,
            "f0_median_st": med,
            "f0_range_st": rng,
            "f0_std_st": std,
            "vocal_centroid": cent,
            "n_voiced_frames": nvoiced,
        })
    except Exception as e:  # noqa: BLE001 — record failure, keep the batch going
        rec["error"] = repr(e)
        for k in FEATURE_COLS:
            rec.setdefault(k, np.nan)
    return rec


def build_targets():
    """(tag, band, idx, song) for every catalog row that has a vocals.wav on disk."""
    df = pd.read_csv(CATALOG_CSV)
    targets = []
    for _, r in df.iterrows():
        tag = str(r["tag"])
        # idx is encoded in the tag suffix ({band}__{idx:03d}); catalog has no idx col.
        try:
            idx = int(tag.split("__")[1])
        except (IndexError, ValueError):
            idx = -1
        voc = os.path.join(STEMS_DIR, tag, "vocals.wav")
        if not os.path.isfile(voc):
            print(f"[warn] missing vocals.wav for {tag} — skipped", flush=True)
            continue
        targets.append((tag, str(r["band"]), idx, str(r["song"])))
    return targets


def save_progress(step, n_total, n_done, status):
    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "step": step,
        "n_total": n_total,
        "n_done": n_done,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def run(out_csv, targets, n_jobs, step_name):
    """Batched parallel extraction with resume + per-batch append."""
    os.makedirs(OUT_DIR, exist_ok=True)

    done_tags = set()
    if os.path.isfile(out_csv):
        prev = pd.read_csv(out_csv)
        done_tags = set(prev["tag"].astype(str))
        print(f"[extract] resuming — {len(done_tags)} tracks already in {os.path.basename(out_csv)}",
              flush=True)
    else:
        pd.DataFrame(columns=COLS).to_csv(out_csv, index=False, encoding="utf-8")

    pending = [t for t in targets if t[0] not in done_tags]
    n_total = len(targets)
    n_done = len(done_tags)
    print(f"[extract] {n_total} targets, {n_done} done, {len(pending)} pending "
          f"(n_jobs={n_jobs}, batch={BATCH_SIZE})", flush=True)
    save_progress(step_name, n_total, n_done, "in_progress")

    problems = []
    t0 = time.time()
    for b_start in range(0, len(pending), BATCH_SIZE):
        batch = pending[b_start:b_start + BATCH_SIZE]
        bt0 = time.time()
        results = Parallel(n_jobs=n_jobs, backend="loky")(
            delayed(extract_one)(task) for task in batch
        )
        # append this batch (resume-safe)
        df_batch = pd.DataFrame(results)
        for k in COLS:
            if k not in df_batch.columns:
                df_batch[k] = np.nan
        df_batch[COLS].to_csv(out_csv, mode="a", header=False, index=False, encoding="utf-8")

        for rec in results:
            if rec.get("error"):
                problems.append(f"{rec['tag']}: EXCEPTION {rec['error']}")
            else:
                for k in FEATURE_COLS:
                    v = rec.get(k)
                    if isinstance(v, float) and not np.isfinite(v):
                        problems.append(f"{rec['tag']}: {k} is NaN/inf")

        n_done += len(batch)
        dt = time.time() - bt0
        save_progress(step_name, n_total, n_done, "in_progress")
        print(f"[extract] batch {b_start // BATCH_SIZE + 1}: {len(batch)} tracks in "
              f"{dt:.1f}s ({dt / max(len(batch), 1):.2f}s/track) — {n_done}/{n_total} done",
              flush=True)

    total_dt = time.time() - t0
    final = pd.read_csv(out_csv)
    nan_cells = int(final[FEATURE_COLS].isna().sum().sum())
    status = "done" if (len(final) >= n_total and not problems) else "done_with_problems"
    save_progress(step_name, n_total, len(final), status)

    print(f"\n[extract] {os.path.basename(out_csv)} now has {len(final)} rows (target {n_total})",
          flush=True)
    print(f"[extract] wall time this run: {total_dt:.1f}s", flush=True)
    print(f"[extract] NaN cells in feature columns: {nan_cells}", flush=True)
    if problems:
        print(f"[extract] PROBLEMS this run ({len(problems)}):", flush=True)
        for p in problems:
            print("  ", p, flush=True)
    return final, problems, total_dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=int, default=0,
                    help="process only the first N tracks into vocal_features_smoke.csv")
    ap.add_argument("--n-jobs", type=int, default=-1)
    args = ap.parse_args()

    targets = build_targets()
    print(f"[extract] built {len(targets)} targets from catalog", flush=True)

    if args.smoke > 0:
        smoke_targets = targets[:args.smoke]
        # fresh smoke file each run so timing is clean
        if os.path.isfile(SMOKE_CSV):
            os.remove(SMOKE_CSV)
        print(f"[extract] SMOKE mode — {len(smoke_targets)} tracks -> "
              f"{os.path.basename(SMOKE_CSV)}", flush=True)
        final, problems, total_dt = run(SMOKE_CSV, smoke_targets, args.n_jobs, "smoke")
        return 0 if not problems else 1

    final, problems, total_dt = run(OUT_CSV, targets, args.n_jobs, "full_extract")
    return 0 if (len(final) == len(targets) and not problems) else 1


if __name__ == "__main__":
    sys.exit(main())
