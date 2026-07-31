"""Compute 3 candidate valence features from chord sequences.

DESIGN.md §4 — Only these 3 features, no more:
1. pct_major: Ratio of beats assigned to major chords
2. chord_change_rate: Chords per minute (harmonic rhythm)
3. borrowed_chord_rate: Fraction of chords outside diatonic set of estimated key

Output: out/chord_features.csv (tag, pct_major, chord_change_rate, borrowed_chord_rate, est_key)
"""
import json
from pathlib import Path

import pandas as pd
import numpy as np

from config import OUT_DIR, STEMS_BASE, DIATONIC_POOLS, PITCH_CLASSES


def parse_chord_root_to_index(root_str: str) -> int:
    """
    Convert chord root string (e.g., 'C', 'C#', 'D', ...) to chromagram index (0-11).
    """
    root_str = root_str.strip()
    try:
        return PITCH_CLASSES.index(root_str)
    except ValueError:
        raise ValueError(f"Unknown chord root: {root_str}")


def compute_features_for_song(tag: str, chord_seqs_df: pd.DataFrame, progress: dict) -> dict:
    """
    Compute 3 features for a single song.

    Args:
        tag: Song identifier
        chord_seqs_df: Filtered chord_sequences.csv rows for this song
        progress: Cached metadata (est_key, tempo_bpm, n_beats) from chord extraction

    Returns:
        Dict with pct_major, chord_change_rate, borrowed_chord_rate, est_key
    """
    if len(chord_seqs_df) == 0:
        raise ValueError(f"No chord sequences for {tag}")

    # Get estimated key and tempo from progress
    metadata = progress.get("processed", {}).get(tag, {})
    est_key = metadata.get("est_key", "Cmaj")
    tempo_bpm = metadata.get("tempo_bpm", 120.0)

    # Feature 1: pct_major
    n_beats = len(chord_seqs_df)
    major_beats = (chord_seqs_df["chord_quality"] == "maj").sum()
    pct_major = major_beats / n_beats if n_beats > 0 else 0.0

    # Feature 2: chord_change_rate
    # Count chord changes in the sequence.
    # BUGFIX: compare full chord identity (root AND quality), not root alone.
    # A change from e.g. "Cmaj" to "Cmin" (same root, different quality) is a
    # real chord change but was previously invisible to this comparison.
    chord_changes = 0
    prev_chord = None
    for _, row in chord_seqs_df.iterrows():
        current_chord = (row["chord_root"], row["chord_quality"])
        if prev_chord is not None and current_chord != prev_chord:
            chord_changes += 1
        prev_chord = current_chord

    # Convert beats to minutes.
    # BUGFIX: tempo_bpm is beats-per-MINUTE, so minutes = beats / tempo_bpm.
    # The original formula `n_beats / (tempo_bpm / 60)` divides beats by
    # beats-per-SECOND, which yields the duration in seconds (60x too large
    # when mislabeled as minutes), making chord_change_rate 60x too small.
    duration_minutes = n_beats / tempo_bpm if tempo_bpm > 0 else 1.0
    chord_change_rate = chord_changes / duration_minutes if duration_minutes > 0 else 0.0

    # Feature 3: borrowed_chord_rate
    # Get diatonic pool for estimated key.
    # BUGFIX: DIATONIC_POOLS now stores (root, quality) pairs, not root-only,
    # so a same-root borrowed-quality chord (e.g. tonic major borrowed into a
    # minor key) is correctly flagged as non-diatonic. See config.py
    # _get_diatonic_chords docstring for rationale.
    diatonic_pairs = DIATONIC_POOLS.get(est_key, set())

    if len(diatonic_pairs) == 0:
        # Fallback if key not recognized
        borrowed_chord_rate = 0.0
    else:
        borrowed_count = 0
        for _, row in chord_seqs_df.iterrows():
            root_idx = parse_chord_root_to_index(row["chord_root"])
            if (root_idx, row["chord_quality"]) not in diatonic_pairs:
                borrowed_count += 1

        borrowed_chord_rate = borrowed_count / n_beats if n_beats > 0 else 0.0

    return {
        "tag": tag,
        "pct_major": float(pct_major),
        "chord_change_rate": float(chord_change_rate),
        "borrowed_chord_rate": float(borrowed_chord_rate),
        "est_key": est_key,
    }


def main():
    # Load chord sequences
    chord_seq_path = OUT_DIR / "chord_sequences.csv"
    if not chord_seq_path.exists():
        raise FileNotFoundError(
            f"Chord sequences not found. Run 02_extract_chords.py first."
        )

    chord_seq_df = pd.read_csv(chord_seq_path)
    print(f"Loaded {len(chord_seq_df)} beat-level chord records")

    # Load progress metadata
    progress_path = OUT_DIR / "chord_progress.json"
    if not progress_path.exists():
        raise FileNotFoundError("Chord progress metadata not found")

    with open(progress_path, "r") as f:
        progress = json.load(f)

    # Load pilot song list to iterate in order
    pilot_path = OUT_DIR / "pilot_song_list.csv"
    if not pilot_path.exists():
        raise FileNotFoundError("Pilot song list not found")

    pilot_df = pd.read_csv(pilot_path)

    # Compute features
    output_rows = []
    for idx, row in pilot_df.iterrows():
        tag = row["tag"]
        print(f"[{idx + 1}/{len(pilot_df)}] {tag}...", end=" ", flush=True)

        # Filter chord sequences for this song
        song_chords = chord_seq_df[chord_seq_df["tag"] == tag]

        if len(song_chords) == 0:
            print("WARNING: No chord sequences found, skipping")
            continue

        try:
            features = compute_features_for_song(tag, song_chords, progress)
            output_rows.append(features)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            continue

    # Save features
    if output_rows:
        output_df = pd.DataFrame(output_rows)
        output_path = OUT_DIR / "chord_features.csv"
        output_df.to_csv(output_path, index=False)
        print(f"\nSaved {len(output_df)} feature records to {output_path}")
        print(output_df.to_string())
    else:
        print("No features computed")


if __name__ == "__main__":
    main()
