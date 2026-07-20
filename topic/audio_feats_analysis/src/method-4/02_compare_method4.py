#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-4: Step 2 — Evaluate method-4 selection against bestdori official BPM.

Merges method4_selected.csv with bestdori_bpm.csv (inner join).
For each threshold, computes RMS error, accuracy (±4%), and count of switched songs.

Output: bpm_method4_validation.csv
"""

import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

SELECTED_CSV = "topic/audio_feats_analysis/out/bpm_method4_selected.csv"
BESTDORI_CSV = "topic/audio_feats_analysis/out/bestdori_bpm.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_method4_validation.csv"


if __name__ == "__main__":
    print("=" * 80)
    print("Method-4 Step 2: Validation Against Bestdori BPM")
    print("=" * 80)
    print()

    # Load data
    print(f"Loading {SELECTED_CSV}...")
    selected_df = pd.read_csv(SELECTED_CSV)
    print(f"  Rows: {len(selected_df)}")

    print(f"Loading {BESTDORI_CSV}...")
    bestdori_df = pd.read_csv(BESTDORI_CSV)
    print(f"  Rows: {len(bestdori_df)}")
    print()

    # Merge on idx, tag
    print("Merging on (idx, tag)...")
    merged = selected_df.merge(bestdori_df[["idx", "tag", "official_bpm"]],
                                on=["idx", "tag"],
                                how="inner")
    print(f"  Merged rows: {len(merged)}")
    print()

    # Compute error
    merged["err_bpm"] = merged["selected_bpm_m4"] - merged["official_bpm"]
    merged["err_abs"] = merged["err_bpm"].abs()
    merged["err_pct"] = (merged["err_abs"] / merged["official_bpm"]) * 100

    # Per-threshold metrics
    thresholds = sorted(merged["threshold"].unique())
    validation_results = []

    print("Validation Results (Method-4)")
    print("-" * 100)
    print(f"{'Threshold':>12} {'N (songs)':>12} {'RMS (BPM)':>12} {'Acc±4% (%)':>14} {'Switched':>10}")
    print("-" * 100)

    for tau in thresholds:
        subset = merged[merged["threshold"] == tau]
        n = len(subset)

        rms = np.sqrt(np.mean(subset["err_bpm"] ** 2))
        acc1 = (subset["err_pct"] <= 4).sum() / n
        n_switched = subset["switched"].sum()

        validation_results.append({
            "threshold": tau,
            "n_songs": n,
            "rms_bpm": rms,
            "accuracy_4pct": acc1 * 100,
            "n_switched": n_switched
        })

        print(f"{tau:12.2f} {n:12d} {rms:12.2f} {acc1*100:13.1f}% {n_switched:10d}")

    print("-" * 100)
    print()

    # Find best threshold (by RMS)
    best_idx = np.argmin([v["rms_bpm"] for v in validation_results])
    best_result = validation_results[best_idx]

    print("Best Threshold (by RMS):")
    print(f"  Threshold:    {best_result['threshold']:.2f}")
    print(f"  RMS Error:    {best_result['rms_bpm']:.2f} BPM")
    print(f"  Accuracy±4%:  {best_result['accuracy_4pct']:.1f}%")
    print(f"  Switched:     {best_result['n_switched']} songs")
    print()

    # Save validation results
    val_df = pd.DataFrame(validation_results)
    print(f"Saving validation results to {OUTPUT_CSV}...")
    val_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(val_df)} threshold results")
    print()
