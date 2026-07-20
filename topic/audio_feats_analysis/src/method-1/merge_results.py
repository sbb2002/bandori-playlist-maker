#!/usr/bin/env python3
"""
Merge ACF symmetric check results into the main audio_feats.csv.

This script:
1. Re-processes all 337 ambiguous songs
2. Computes pulse_acf_half, pulse_ratio_down, pulse_recommend_half
3. Merges results into audio_feats.csv (661 rows, 3 new columns)
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import librosa


# Configuration
SR = 22050
HOP = 256
DRUMS_ROOT = "C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_drums"
CSV_PATH = "topic/audio_feats_analysis/out/audio_feats.csv"
TAU_THRESHOLD = 0.96
MIN_BPM = 85.0


def n_candidates(bpm):
    """Count how many tempo candidates (base * 2^n) fall in [85, 220] range."""
    LO, HI = 85.0, 220.0
    return sum(1 for n in [-2, -1, 0, 1, 2] if LO <= bpm * (2 ** n) <= HI)


def acf_at(acf, bpm):
    """Get ACF value at given BPM."""
    lag = int(round((60.0 / bpm) * SR / HOP))
    if 1 <= lag < len(acf):
        return float(acf[lag])
    return 0.0


def compute_acf_half(row, drums_root=DRUMS_ROOT):
    """Compute ACF(base/2) and pulse_ratio_down for a single song."""
    tag = row['tag']
    base_bpm = row['drum_tempo_bpm']
    pulse_acf_slow = row['pulse_acf_slow']

    # Validate input
    if pd.isna(base_bpm) or pd.isna(pulse_acf_slow) or pulse_acf_slow == 0:
        return None

    # Load drum audio
    audio_path = os.path.join(drums_root, f"{tag}.wav")
    if not os.path.exists(audio_path):
        return None

    try:
        y, _ = librosa.load(audio_path, sr=SR, mono=True)
        onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        acf = librosa.autocorrelate(onset_env)
        acf = acf / (acf[0] or 1.0)

        acf_half = acf_at(acf, base_bpm / 2.0)
        pulse_ratio_down = acf_half / pulse_acf_slow if pulse_acf_slow > 0 else 0.0

        recommend_half = (
            pulse_ratio_down >= TAU_THRESHOLD and
            (base_bpm / 2.0) >= MIN_BPM
        )

        return {
            'pulse_acf_half': acf_half,
            'pulse_ratio_down': pulse_ratio_down,
            'pulse_recommend_half': recommend_half
        }

    except Exception as e:
        return None


def main():
    # Load data
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} songs from {CSV_PATH}")

    # Initialize result columns
    for col in ['pulse_acf_half', 'pulse_ratio_down', 'pulse_recommend_half']:
        df[col] = np.nan

    # Find ambiguous songs
    df['_n_cand'] = df['drum_tempo_bpm'].apply(n_candidates)
    ambiguous_idx = df[df['_n_cand'] == 2].index
    print(f"Found {len(ambiguous_idx)} ambiguous songs (2 candidates)")

    # Process each ambiguous song
    processed = 0
    start_time = time.perf_counter()

    for i, idx in enumerate(ambiguous_idx):
        if (i + 1) % 50 == 0:
            print(f"[{i+1:3d}/{len(ambiguous_idx)}]", flush=True)

        row = df.loc[idx]
        result = compute_acf_half(row)

        if result:
            for key, val in result.items():
                df.at[idx, key] = val
            processed += 1

    elapsed = time.perf_counter() - start_time

    # Report results
    print(f"\n{'='*60}")
    print(f"MERGE RESULTS")
    print(f"{'='*60}")
    print(f"Total elapsed time: {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
    print(f"Successfully processed: {processed}/{len(ambiguous_idx)} songs")

    # Validation checks
    non_null_half = df['pulse_acf_half'].notna().sum()
    non_null_down = df['pulse_ratio_down'].notna().sum()
    non_null_recommend = df['pulse_recommend_half'].notna().sum()

    print(f"\nNew columns statistics:")
    print(f"  pulse_acf_half: {non_null_half} non-null values")
    print(f"  pulse_ratio_down: {non_null_down} non-null values")
    print(f"  pulse_recommend_half: {non_null_recommend} non-null values")

    if non_null_half == 337 and non_null_down == 337 and non_null_recommend == 337:
        print(f"\n[OK] All 337 ambiguous songs processed")
    else:
        print(f"\n[WARN] Some songs missing: expected 337, got {min(non_null_half, non_null_down, non_null_recommend)}")

    # Verification
    print(f"\n{'='*60}")
    print(f"VERIFICATION (4 test songs):")
    print(f"{'='*60}")

    test_tags = ['roselia__638', 'roselia__620', 'roselia__595', 'mugendai_mutype__243']
    expected = {
        'roselia__638': (True, "should recommend half (89.1 is correct)"),
        'roselia__620': (False, "should NOT recommend half (172.3 is correct)"),
        'roselia__595': (False, "should NOT recommend half (172.3 is correct)"),
        'mugendai_mutype__243': (False, "should NOT recommend half (178.2 is correct)")
    }

    for tag in test_tags:
        rows = df[df['tag'] == tag]
        if len(rows) == 0:
            print(f"{tag}: NOT FOUND")
        else:
            row = rows.iloc[0]
            base = row['drum_tempo_bpm']
            expect_recommend = expected[tag][0]
            reason = expected[tag][1]
            actual_recommend = row['pulse_recommend_half']
            ratio = row['pulse_ratio_down']

            status = "OK" if actual_recommend == expect_recommend else "MISMATCH"
            print(f"\n{tag}:")
            print(f"  base={base:.1f}, half={base/2:.1f}")
            print(f"  pulse_ratio_down={ratio:.4f}")
            print(f"  pulse_recommend_half={actual_recommend} (expected: {expect_recommend})")
            print(f"  reason: {reason}")
            print(f"  [{status}]")

    # Save merged CSV
    output_cols = list(df.columns)
    output_cols.remove('_n_cand')  # Drop helper column
    df_out = df[output_cols]
    df_out.to_csv(CSV_PATH, index=False)
    print(f"\n{'='*60}")
    print(f"Merged CSV saved to: {CSV_PATH}")
    print(f"Total rows: {len(df_out)}")
    print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
