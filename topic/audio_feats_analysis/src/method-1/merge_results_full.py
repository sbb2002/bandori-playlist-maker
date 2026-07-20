#!/usr/bin/env python3
"""
Compute ACF(base/2) for ALL 661 songs and merge into audio_feats.csv.

Previous run (merge_results.py) only covered the 337 songs where base/2 fell
within [85,220] for some 2-candidate window — that was a sub-local run without
audio access, so it only processed songs where the down-candidate mattered.
This is the main local (has bandori-song-sorter audio_drums), so we recompute
pulse_acf_half/pulse_ratio_down/pulse_recommend_half for all 661 songs,
regardless of whether base/2 lands in the genre BPM range.
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import librosa


SR = 22050
HOP = 256
DRUMS_ROOT = "C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_drums"
CSV_PATH = "topic/audio_feats_analysis/out/audio_feats.csv"
TAU_THRESHOLD = 0.96
MIN_BPM = 85.0


def acf_at(acf, bpm):
    lag = int(round((60.0 / bpm) * SR / HOP))
    if 1 <= lag < len(acf):
        return float(acf[lag])
    return 0.0


def compute_acf_half(row, drums_root=DRUMS_ROOT):
    tag = row['tag']
    base_bpm = row['drum_tempo_bpm']
    pulse_acf_slow = row['pulse_acf_slow']

    if pd.isna(base_bpm) or pd.isna(pulse_acf_slow) or pulse_acf_slow == 0:
        return None

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
        print(f"  ERROR processing {tag}: {e}", file=sys.stderr)
        return None


def main():
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} songs from {CSV_PATH}")

    for col in ['pulse_acf_half', 'pulse_ratio_down', 'pulse_recommend_half']:
        df[col] = np.nan

    processed = 0
    start_time = time.perf_counter()

    for i, idx in enumerate(df.index):
        if (i + 1) % 50 == 0:
            elapsed_so_far = time.perf_counter() - start_time
            print(f"[{i+1:3d}/{len(df)}] elapsed={elapsed_so_far:.1f}s", flush=True)

        row = df.loc[idx]
        result = compute_acf_half(row)

        if result:
            for key, val in result.items():
                df.at[idx, key] = val
            processed += 1

    elapsed = time.perf_counter() - start_time

    print(f"\n{'='*60}")
    print(f"FULL MERGE RESULTS")
    print(f"{'='*60}")
    print(f"Total elapsed time: {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
    print(f"Successfully processed: {processed}/{len(df)} songs")

    non_null_half = df['pulse_acf_half'].notna().sum()
    print(f"\npulse_acf_half non-null: {non_null_half}/{len(df)}")

    df.to_csv(CSV_PATH, index=False)
    print(f"\nMerged CSV saved to: {CSV_PATH}")
    print(f"Total rows: {len(df)}")


if __name__ == '__main__':
    sys.exit(main())
