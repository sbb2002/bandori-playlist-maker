#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-3: Step 2 — Select BPM using pure octave multipliers (2^n).

Uses ONLY OCTAVE_MULTIPLIERS (0.25, 0.5, 1.0, 2.0, 4.0).
Selects candidate with highest ACF value among valid (non-NaN) candidates.
Computes margin = (top1_acf - top2_acf) / top1_acf for downstream hemiola fallback.

No bestdori data used (selection only).

Output: bpm_method3_selected.csv
"""

import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

# Constants
OCTAVE_MULTIPLIERS = [0.25, 0.5, 1.0, 2.0, 4.0]
INPUT_CSV = "topic/audio_feats_analysis/out/bpm_candidates_v2.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_method3_selected.csv"


def format_multiplier_label(m):
    """Format multiplier for column naming."""
    return str(float(m))


def select_bpm(row):
    """
    Select best BPM from OCTAVE_MULTIPLIERS candidates.

    Returns: dict with selection results
    """
    idx = row["idx"]
    tag = row["tag"]

    # Collect valid candidates from OCTAVE_MULTIPLIERS
    candidates = []
    for m in OCTAVE_MULTIPLIERS:
        label = format_multiplier_label(m)
        acf_col = f"cand_{label}_acf"
        bpm_col = f"cand_{label}_bpm"

        if acf_col in row and not pd.isna(row[acf_col]):
            candidates.append((m, row[bpm_col], row[acf_col]))

    result = {
        "idx": idx,
        "tag": tag,
    }

    if not candidates:
        # No valid candidates (should not happen in normal flow)
        result["selected_bpm_m3"] = np.nan
        result["selected_mult_m3"] = np.nan
        result["top1_acf"] = np.nan
        result["top2_acf"] = np.nan
        result["margin"] = np.nan
    else:
        # Sort by ACF descending
        candidates.sort(key=lambda c: c[2], reverse=True)

        # Top 1
        top1_mult, top1_bpm, top1_acf = candidates[0]
        result["selected_bpm_m3"] = top1_bpm
        result["selected_mult_m3"] = top1_mult
        result["top1_acf"] = top1_acf

        # Top 2 (if exists)
        if len(candidates) >= 2:
            top2_acf = candidates[1][2]
            result["top2_acf"] = top2_acf
            result["margin"] = (top1_acf - top2_acf) / top1_acf
        else:
            # Only 1 valid candidate (or fewer multipliers available)
            result["top2_acf"] = np.nan
            result["margin"] = np.nan

    return result


if __name__ == "__main__":
    print("=" * 80)
    print("Method-3 Step 2: Select BPM (Octave Multipliers)")
    print("=" * 80)
    print()

    # Load candidates
    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    print(f"Total songs: {len(df)}")
    print(f"Octave multipliers: {OCTAVE_MULTIPLIERS}")
    print()

    # Select BPM for each song
    results = []
    for _, row in df.iterrows():
        result = select_bpm(row)
        results.append(result)

    # Convert to DataFrame
    results_df = pd.DataFrame(results)

    # Save output
    print(f"Saving results to {OUTPUT_CSV}...")
    results_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(results_df)} rows")
    print()

    # Summary
    n_ok = results_df["selected_bpm_m3"].notna().sum()
    n_with_margin = results_df["margin"].notna().sum()
    print("Summary:")
    print(f"  Songs with selection: {n_ok}")
    print(f"  Songs with margin (2+ candidates): {n_with_margin}")
    print()
