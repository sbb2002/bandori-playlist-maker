#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-3: Extended BPM candidates using ACF argmax selection.

Expands multiplier candidates from 2^n to {0.5, 2/3, 1.0, 1.5, 2.0},
then selects the BPM with highest onset-envelope ACF value.
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
BPM_LO = 85.0
BPM_HI = 220.0
MULTIPLIERS = [0.5, 2/3, 1.0, 1.5, 2.0]
DRUMS_ROOT = "C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_drums"
INPUT_CSV = "topic/audio_feats_analysis/out/audio_feats.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_extended_candidates.csv"

def acf_at(acf, bpm, sr=SR, hop=HOP):
    """Compute ACF value at a given BPM."""
    lag = int(round((60.0 / bpm) * sr / hop))
    if 1 <= lag < len(acf):
        return float(acf[lag])
    return 0.0

def process_song(row, drums_root=DRUMS_ROOT):
    """
    Process a single song: compute ACF at each multiplier candidate,
    select the one with highest ACF value.

    Returns: dict with results, or None if audio missing.
    """
    idx = row["idx"]
    tag = row["tag"]
    base_bpm = row["drum_tempo_bpm"]

    audio_path = os.path.join(drums_root, f"{tag}.wav")
    if not os.path.exists(audio_path):
        return {
            "idx": idx,
            "tag": tag,
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base_bpm,
            "n_candidates_in_range": 0,
            "base_in_range": False,
            "selected_multiplier": None,
            "selected_bpm": None,
            "selected_acf": None,
            "audio_status": "missing"
        }

    try:
        # Load audio and compute onset-envelope ACF
        y, _ = librosa.load(audio_path, sr=SR, mono=True)
        onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        acf = librosa.autocorrelate(onset_env)
        acf = acf / (acf[0] if acf[0] > 0 else 1.0)

        # Evaluate all candidates
        candidates = []
        candidate_details = {}  # For diagnostic columns

        for m in MULTIPLIERS:
            bpm = base_bpm * m
            if BPM_LO <= bpm <= BPM_HI:
                acf_val = acf_at(acf, bpm)
                candidates.append((m, bpm, acf_val))
                candidate_details[f"cand_{m:.3f}_bpm"] = bpm
                candidate_details[f"cand_{m:.3f}_acf"] = acf_val
            else:
                # Out of range: record NaN
                candidate_details[f"cand_{m:.3f}_bpm"] = np.nan
                candidate_details[f"cand_{m:.3f}_acf"] = np.nan

        # If no candidates in range
        if not candidates:
            result = {
                "idx": idx,
                "tag": tag,
                "band": row["band"],
                "song": row["song"],
                "drum_tempo_bpm": base_bpm,
                "n_candidates_in_range": 0,
                "base_in_range": False,
                "selected_multiplier": 1.0,
                "selected_bpm": base_bpm,
                "selected_acf": None,
                "audio_status": "ok"
            }
        else:
            # Select candidate with highest ACF
            best = max(candidates, key=lambda c: c[2])
            result = {
                "idx": idx,
                "tag": tag,
                "band": row["band"],
                "song": row["song"],
                "drum_tempo_bpm": base_bpm,
                "n_candidates_in_range": len(candidates),
                "base_in_range": True,
                "selected_multiplier": best[0],
                "selected_bpm": best[1],
                "selected_acf": best[2],
                "audio_status": "ok"
            }

        # Add diagnostic columns
        result.update(candidate_details)
        return result

    except Exception as e:
        return {
            "idx": idx,
            "tag": tag,
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base_bpm,
            "n_candidates_in_range": 0,
            "base_in_range": False,
            "selected_multiplier": None,
            "selected_bpm": None,
            "selected_acf": None,
            "audio_status": f"error: {str(e)[:50]}"
        }

if __name__ == "__main__":
    print("=" * 80)
    print("Method-3: Extended BPM Candidates (ACF argmax)")
    print("=" * 80)
    print()

    # Load input
    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    print(f"Total songs: {len(df)}")
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
    print(f"  Errors: {(results_df['audio_status'].str.startswith('error')).sum()}")
    print()
