#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-4: Step 1 — Select BPM with margin-based hemiola fallback.

Uses method-3 selection as base. For each song and threshold tau:
  - If margin >= tau: keep method-3 BPM
  - If margin < tau: try hemiola candidates (2/3, 1.5) and pick highest ACF
    - If both hemiola candidates are invalid (NaN): fallback to method-3

Threshold sweep: [0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]

No bestdori data used (selection only).

Output: bpm_method4_selected.csv (long format: 661 songs × 7 thresholds = 4627 rows)
"""

import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

# Constants
HEMIOLA_MULTIPLIERS = [2/3, 1.5]
THRESHOLDS = [0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]

CANDIDATES_CSV = "topic/audio_feats_analysis/out/bpm_candidates_v2.csv"
METHOD3_CSV = "topic/audio_feats_analysis/out/bpm_method3_selected.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_method4_selected.csv"


def format_multiplier_label(m):
    """Format multiplier for column naming."""
    if m == 2/3:
        return "0.667"
    elif m == 1.5:
        return "1.5"
    else:
        return str(float(m))


def select_bpm_with_threshold(row_cand, row_m3, threshold):
    """
    Select BPM for a given threshold.

    Returns: (selected_bpm_m4, switched)
    """
    m3_bpm = row_m3["selected_bpm_m3"]
    m3_margin = row_m3["margin"]

    # If no margin info or margin >= threshold: use method-3
    if pd.isna(m3_margin) or m3_margin >= threshold:
        return (m3_bpm, False)

    # margin < threshold: try hemiola fallback
    hemiola_candidates = []
    for m in HEMIOLA_MULTIPLIERS:
        label = format_multiplier_label(m)
        acf_col = f"cand_{label}_acf"
        bpm_col = f"cand_{label}_bpm"

        if acf_col in row_cand and not pd.isna(row_cand[acf_col]):
            hemiola_candidates.append((row_cand[bpm_col], row_cand[acf_col]))

    if not hemiola_candidates:
        # No valid hemiola candidates: fallback to method-3
        return (m3_bpm, False)

    # Pick hemiola candidate with highest ACF
    best_bpm = max(hemiola_candidates, key=lambda c: c[1])[0]
    return (best_bpm, True)


if __name__ == "__main__":
    print("=" * 80)
    print("Method-4 Step 1: Select BPM with Margin-Based Hemiola Fallback")
    print("=" * 80)
    print()

    # Load data
    print(f"Loading {CANDIDATES_CSV}...")
    cand_df = pd.read_csv(CANDIDATES_CSV)
    print(f"  Rows: {len(cand_df)}")

    print(f"Loading {METHOD3_CSV}...")
    m3_df = pd.read_csv(METHOD3_CSV)
    print(f"  Rows: {len(m3_df)}")

    print(f"Thresholds: {THRESHOLDS}")
    print()

    # Process each song and threshold
    results = []
    for (idx_c, row_c), (idx_m3, row_m3) in zip(cand_df.iterrows(), m3_df.iterrows()):
        # Verify alignment
        assert row_c["idx"] == row_m3["idx"], f"Index mismatch at row {idx_c}"
        assert row_c["tag"] == row_m3["tag"], f"Tag mismatch at row {idx_c}"

        idx = row_c["idx"]
        tag = row_c["tag"]

        # For each threshold
        for tau in THRESHOLDS:
            bpm_m4, switched = select_bpm_with_threshold(row_c, row_m3, tau)

            results.append({
                "idx": idx,
                "tag": tag,
                "threshold": tau,
                "selected_bpm_m4": bpm_m4,
                "switched": switched
            })

    # Convert to DataFrame
    results_df = pd.DataFrame(results)

    # Save output
    print(f"Saving results to {OUTPUT_CSV}...")
    results_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(results_df)} rows")
    print()

    # Summary
    print("Summary:")
    for tau in THRESHOLDS:
        subset = results_df[results_df["threshold"] == tau]
        n_switched = subset["switched"].sum()
        print(f"  Threshold {tau:.2f}: {n_switched:3d} songs switched to hemiola")
    print()
