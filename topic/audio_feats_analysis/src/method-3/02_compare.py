#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-3 Validation: Compare extended-candidate BPM with official Bestdori BPM.
"""

import os
import numpy as np
import pandas as pd

INPUT_CANDIDATES = "topic/audio_feats_analysis/out/bpm_extended_candidates.csv"
INPUT_BESTDORI = "topic/audio_feats_analysis/out/bestdori_bpm.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_extended_validation.csv"

if __name__ == "__main__":
    print("=" * 80)
    print("Method-3 Validation: ACF argmax vs Bestdori Official BPM")
    print("=" * 80)
    print()

    # Load data
    print(f"Loading {INPUT_CANDIDATES}...")
    cand_df = pd.read_csv(INPUT_CANDIDATES)
    print(f"  Candidates: {len(cand_df)} rows")

    print(f"Loading {INPUT_BESTDORI}...")
    best_df = pd.read_csv(INPUT_BESTDORI)
    print(f"  Bestdori: {len(best_df)} rows")
    print()

    # Merge on idx, tag
    print("Merging on (idx, tag)...")
    merged = pd.merge(
        cand_df,
        best_df[["idx", "tag", "official_bpm"]],
        on=["idx", "tag"],
        how="inner"
    )
    print(f"  Matched: {len(merged)} rows")
    print()

    # Compute error
    merged["err_bpm"] = merged["selected_bpm"] - merged["official_bpm"]

    # Statistics
    rms_bpm = float(np.sqrt((merged["err_bpm"]**2).mean()))
    acc1 = (((merged["selected_bpm"] - merged["official_bpm"]).abs() / merged["official_bpm"]) <= 0.04).mean()

    print("=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    print()
    print(f"N (matched songs):            {len(merged)}")
    print(f"RMS(BPM) error:               {rms_bpm:.2f} BPM")
    print(f"  (vs baseline method-2:      23.61 BPM)")
    pct_change = (rms_bpm - 23.61) / 23.61 * 100
    print(f"  Δ:                          {pct_change:+.1f}%")
    print()
    print(f"Accuracy (±4%):               {acc1:.1%}")
    print(f"  (vs baseline method-2:      92.5%)")
    print()

    # Multiplier distribution
    print("Selected Multiplier Distribution:")
    mult_counts = merged["selected_multiplier"].value_counts().sort_index()
    for mult, count in mult_counts.items():
        pct = count / len(merged) * 100
        print(f"  {mult:.3f}:  {count:3d} songs ({pct:5.1f}%)")
    print()

    # Top 15 errors
    print("Top 15 Largest Errors (sorted by |err_bpm|):")
    print()
    top_errors = merged.nlargest(15, "err_bpm").copy()
    # Alternate sign for display (show absolute errors)
    top_errors_display = pd.concat([
        merged.nlargest(15, "err_bpm"),
        merged.nsmallest(15, "err_bpm")
    ]).drop_duplicates(subset=["idx"]).sort_values("err_bpm", key=abs, ascending=False).head(15)

    print(f"{'tag':<25} {'band':<15} {'song':<35} {'drum_bpm':>9} {'selected_bpm':>12} {'mult':>6} {'official_bpm':>12} {'err_bpm':>9}")
    print("-" * 135)
    for _, row in top_errors_display.iterrows():
        tag = str(row["tag"])[:24]
        band = str(row["band"])[:14]
        song = str(row["song"])[:34]
        drum_bpm = row["drum_tempo_bpm"]
        sel_bpm = row["selected_bpm"]
        mult = row["selected_multiplier"]
        off_bpm = row["official_bpm"]
        err_bpm = row["err_bpm"]
        print(f"{tag:<25} {band:<15} {song:<35} {drum_bpm:>9.1f} {sel_bpm:>12.1f} {mult:>6.3f} {off_bpm:>12.1f} {err_bpm:>9.1f}")
    print()

    # Save
    print(f"Saving validation results to {OUTPUT_CSV}...")
    merged.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(merged)} rows")
    print()

    print("=" * 80)
    print("Done!")
    print("=" * 80)
