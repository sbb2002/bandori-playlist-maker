#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-3: Step 1 — Compute BPM candidates using ACF.

Generates 7 candidate BPMs per song (0.25, 0.5, 1.0, 2.0, 4.0, 2/3, 1.5 multipliers)
by analyzing the onset-envelope ACF. No range restrictions on BPM.
No bestdori data used (selection step only).

Output: bpm_candidates_v2.csv
"""

import os
import numpy as np
import pandas as pd
import librosa
import warnings

warnings.filterwarnings("ignore")

# Constants
SR = 22050
HOP = 256
OCTAVE_MULTIPLIERS = [0.25, 0.5, 1.0, 2.0, 4.0]
HEMIOLA_MULTIPLIERS = [2/3, 1.5]
ALL_MULTIPLIERS = OCTAVE_MULTIPLIERS + HEMIOLA_MULTIPLIERS  # 7 total

DRUMS_ROOT = "C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_drums"
INPUT_CSV = "topic/audio_feats_analysis/out/audio_feats.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_candidates_v2.csv"


def acf_at(acf, bpm, sr=SR, hop=HOP):
    """
    Compute ACF value at a given BPM.

    Returns:
        float: ACF value if lag is within bounds, None otherwise
    """
    lag = int(round((60.0 / bpm) * sr / hop))
    if 1 <= lag < len(acf):
        return float(acf[lag])
    return None


def format_multiplier_label(m):
    """Format multiplier for column naming."""
    if m == 2/3:
        return "0.667"
    elif m == 1.5:
        return "1.5"
    else:
        return str(float(m))


def process_song(row, drums_root=DRUMS_ROOT):
    """
    Process a single song: compute ACF at each multiplier candidate.

    Returns: dict with results, or None if audio missing.
    """
    idx = row["idx"]
    tag = row["tag"]
    base_bpm = row["drum_tempo_bpm"]

    audio_path = os.path.join(drums_root, f"{tag}.wav")
    if not os.path.exists(audio_path):
        result = {
            "idx": idx,
            "tag": tag,
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base_bpm,
            "audio_status": "missing"
        }
        # Add NaN for all candidates
        for m in ALL_MULTIPLIERS:
            label = format_multiplier_label(m)
            result[f"cand_{label}_bpm"] = np.nan
            result[f"cand_{label}_acf"] = np.nan
        return result

    try:
        # Load audio and compute onset-envelope ACF
        y, _ = librosa.load(audio_path, sr=SR, mono=True)
        onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        acf = librosa.autocorrelate(onset_env)
        acf = acf / (acf[0] if acf[0] > 0 else 1.0)

        result = {
            "idx": idx,
            "tag": tag,
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base_bpm,
            "audio_status": "ok"
        }

        # Evaluate all candidates
        for m in ALL_MULTIPLIERS:
            bpm = base_bpm * m
            acf_val = acf_at(acf, bpm)

            label = format_multiplier_label(m)
            if acf_val is not None:
                result[f"cand_{label}_bpm"] = bpm
                result[f"cand_{label}_acf"] = acf_val
            else:
                # Out of bounds: NaN
                result[f"cand_{label}_bpm"] = np.nan
                result[f"cand_{label}_acf"] = np.nan

        return result

    except Exception as e:
        result = {
            "idx": idx,
            "tag": tag,
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base_bpm,
            "audio_status": f"error: {str(e)[:50]}"
        }
        # Add NaN for all candidates
        for m in ALL_MULTIPLIERS:
            label = format_multiplier_label(m)
            result[f"cand_{label}_bpm"] = np.nan
            result[f"cand_{label}_acf"] = np.nan
        return result


if __name__ == "__main__":
    print("=" * 80)
    print("Method-3 Step 1: Compute BPM Candidates")
    print("=" * 80)
    print()

    # Load input
    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    print(f"Total songs: {len(df)}")
    print(f"Multipliers: {ALL_MULTIPLIERS} ({len(ALL_MULTIPLIERS)} total)")
    print()

    # Process each song
    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        if (i + 1) % 50 == 0:
            print(f"Progress: {i+1}/{len(df)} songs processed...")

        result = process_song(row)
        results.append(result)

    print(f"Progress: {len(df)}/{len(df)} songs processed (complete)")
    print()

    # Convert to DataFrame
    results_df = pd.DataFrame(results)

    # Save output
    print(f"Saving results to {OUTPUT_CSV}...")
    results_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(results_df)} rows")
    print()

    # Summary
    print("Summary:")
    print(f"  OK: {(results_df['audio_status'] == 'ok').sum()}")
    print(f"  Missing audio: {(results_df['audio_status'] == 'missing').sum()}")
    errors = results_df['audio_status'].str.startswith('error', na=False).sum()
    print(f"  Errors: {errors}")
    print()
