#!/usr/bin/env python3
"""
ACF symmetric check: Compute ACF(base/2) and pulse_ratio_down for ambiguous songs.

This script:
1. Identifies 337 songs with exactly 2 tempo candidates in [85, 220] BPM range
2. Computes ACF at base/2 for each candidate
3. Calculates pulse_ratio_down = ACF(base/2) / ACF(base)
4. Determines if base/2 is a better candidate than base (pulse_recommend_half)

For pilot run: first 15 songs only, with timing measurement.
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import librosa


# Configuration
SR = 22050  # Sample rate (must match existing pulse analysis)
HOP = 256   # Hop length (must match existing pulse analysis)
DRUMS_ROOT = "C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_drums"
CSV_PATH = "topic/audio_feats_analysis/out/audio_feats.csv"
PILOT_COUNT = 15  # Set to None to process all ambiguous songs
PROCESS_ALL = True  # Override pilot count to process all 337 songs
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
    """
    Compute ACF(base/2) and pulse_ratio_down for a single song.

    Returns:
        dict with keys: pulse_acf_half, pulse_ratio_down, pulse_recommend_half
        or None if processing failed
    """
    tag = row['tag']
    base_bpm = row['drum_tempo_bpm']
    pulse_acf_slow = row['pulse_acf_slow']

    # Validate input
    if pd.isna(base_bpm) or pd.isna(pulse_acf_slow) or pulse_acf_slow == 0:
        return None

    # Load drum audio
    audio_path = os.path.join(drums_root, f"{tag}.wav")
    if not os.path.exists(audio_path):
        print(f"  WARNING: {audio_path} not found", file=sys.stderr)
        return None

    try:
        y, _ = librosa.load(audio_path, sr=SR, mono=True)

        # Compute onset strength
        onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)

        # Compute autocorrelation
        acf = librosa.autocorrelate(onset_env)
        acf = acf / (acf[0] or 1.0)  # Normalize to [0, 1]

        # Get ACF value at base/2
        acf_half = acf_at(acf, base_bpm / 2.0)

        # Compute ratio: ACF(base/2) / ACF(base)
        pulse_ratio_down = acf_half / pulse_acf_slow if pulse_acf_slow > 0 else 0.0

        # Recommend half if ratio >= 0.96 AND half tempo >= 85 BPM
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
        print(f"  ERROR processing {tag}: {e}", file=sys.stderr)
        return None


def main():
    # Load data
    df = pd.read_csv(CSV_PATH)

    # Find ambiguous songs
    df['_n_cand'] = df['drum_tempo_bpm'].apply(n_candidates)
    ambiguous = df[df['_n_cand'] == 2].copy()

    print(f"Total songs in CSV: {len(df)}")
    print(f"Ambiguous songs (2 candidates): {len(ambiguous)}")

    if PROCESS_ALL:
        to_process = ambiguous.copy()
        print(f"Processing ALL {len(ambiguous)} songs...\n")
    else:
        to_process = ambiguous.head(PILOT_COUNT).copy()
        print(f"Processing first {PILOT_COUNT} for timing measurement...\n")

    # Run on selected songs
    pilot_data = to_process.copy()

    # Initialize result columns
    for col in ['pulse_acf_half', 'pulse_ratio_down', 'pulse_recommend_half']:
        pilot_data[col] = None

    # Measure time
    start_time = time.perf_counter()

    for i, (idx, row) in enumerate(pilot_data.iterrows()):
        tag = row['tag']
        print(f"[{i+1:2d}/{PILOT_COUNT}] Processing {tag}...", end="", flush=True)
        song_start = time.perf_counter()

        result = compute_acf_half(row)
        if result:
            for key, val in result.items():
                pilot_data.at[idx, key] = val
            print(f" DONE ({time.perf_counter() - song_start:.3f}s)")
        else:
            print(f" SKIP")

    end_time = time.perf_counter()
    elapsed = end_time - start_time

    # Report timing
    valid_count = pilot_data['pulse_acf_half'].notna().sum()
    avg_time_per_song = elapsed / valid_count if valid_count > 0 else 0
    total_estimated_time_337 = avg_time_per_song * 337

    print(f"\n{'='*60}")
    print(f"PILOT RESULTS (first {PILOT_COUNT} songs):")
    print(f"{'='*60}")
    print(f"Total elapsed time: {elapsed:.3f} seconds")
    print(f"Successfully processed: {valid_count} songs")
    print(f"Average time per song: {avg_time_per_song:.3f} seconds")
    print(f"\nESTIMATED TIME FOR 337 SONGS: {total_estimated_time_337:.1f} seconds ({total_estimated_time_337/60:.2f} minutes)")

    if total_estimated_time_337 <= 300:
        print(f"[OK] Under 5 minutes -> SAFE TO EXPAND TO FULL 337 SONGS")
    else:
        print(f"[WARN] OVER 5 minutes -> DO NOT EXPAND (would take {total_estimated_time_337/60:.1f} min)")

    print(f"\n{'='*60}")
    print(f"PILOT RESULTS (detailed):")
    print(f"{'='*60}")
    for idx, row in pilot_data.iterrows():
        tag = row['tag']
        base = row['drum_tempo_bpm']
        if pd.notna(row['pulse_acf_half']):
            print(f"{tag}:")
            print(f"  base={base:.1f}, half={base/2:.1f}")
            print(f"  pulse_acf_slow={row['pulse_acf_slow']:.4f}, pulse_acf_half={row['pulse_acf_half']:.4f}")
            print(f"  pulse_ratio_down={row['pulse_ratio_down']:.4f}")
            print(f"  pulse_recommend_half={row['pulse_recommend_half']}")
        else:
            print(f"{tag}: FAILED")

    # Save pilot results
    pilot_output = pilot_data[[
        'tag', 'drum_tempo_bpm', 'pulse_acf_slow',
        'pulse_acf_half', 'pulse_ratio_down', 'pulse_recommend_half'
    ]].copy()
    pilot_output.to_csv('topic/audio_feats_analysis/out/pilot_15_results.csv', index=False)
    print(f"\nPilot results saved to: topic/audio_feats_analysis/out/pilot_15_results.csv")

    return 0 if total_estimated_time_337 <= 300 else 1


if __name__ == '__main__':
    sys.exit(main())
