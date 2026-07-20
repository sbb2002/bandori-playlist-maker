#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method-3: Step 3 — Evaluate method-3 selection against bestdori official BPM.

Merges method3_selected.csv with bestdori_bpm.csv (inner join on idx/tag).
Computes RMS error, accuracy (±4%), and shows top error songs.

Output: bpm_method3_validation.csv
"""

import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

SELECTED_CSV = "topic/audio_feats_analysis/out/bpm_method3_selected.csv"
BESTDORI_CSV = "topic/audio_feats_analysis/out/bestdori_bpm.csv"
OUTPUT_CSV = "topic/audio_feats_analysis/out/bpm_method3_validation.csv"


if __name__ == "__main__":
    print("=" * 80)
    print("Method-3 Step 3: Validation Against Bestdori BPM")
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
    merged["err_bpm"] = merged["selected_bpm_m3"] - merged["official_bpm"]
    merged["err_abs"] = merged["err_bpm"].abs()
    merged["err_pct"] = (merged["err_abs"] / merged["official_bpm"]) * 100

    # Compute metrics
    rms = np.sqrt(np.mean(merged["err_bpm"] ** 2))
    acc1 = (merged["err_pct"] <= 4).sum() / len(merged)

    print("Validation Results (Method-3, n={})".format(len(merged)))
    print("-" * 60)
    print(f"  RMS Error (BPM):  {rms:.2f}")
    print(f"  Accuracy (±4%):   {acc1*100:.1f}%")
    print()

    # Top 15 error songs
    print("Top 15 songs with largest BPM error:")
    print("-" * 80)
    top_err = merged.nlargest(15, "err_abs")[["tag", "official_bpm", "selected_bpm_m3",
                                               "err_bpm", "err_pct", "margin"]]
    for idx, row in top_err.iterrows():
        margin_str = f"{row['margin']:.3f}" if pd.notna(row['margin']) else "NaN"
        print(f"  {row['tag']:20s}  official={row['official_bpm']:6.1f}  "
              f"est={row['selected_bpm_m3']:6.1f}  err={row['err_bpm']:+6.1f}  "
              f"err%={row['err_pct']:5.1f}%  margin={margin_str}")
    print()

    # Save output
    print(f"Saving results to {OUTPUT_CSV}...")
    merged.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved {len(merged)} rows")
    print()
