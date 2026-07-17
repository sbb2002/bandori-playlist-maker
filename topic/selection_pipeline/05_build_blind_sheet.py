"""
Step 5: Build blind evaluation sheet from arm results.

DESIGN.md §4: Combine top-3 from all three arms, remove identity-revealing columns,
shuffle, and produce two outputs:
  1. method3_blind_sheet.csv — for evaluation (score/comment to be filled)
  2. method3_blind_mapping.csv — for unblinding after evaluation

Important (§4c): Print actual unique pair count to console before starting evaluation.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from random import Random

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load arm results
    print("Loading arm results...")
    df_arms = pd.read_csv(config.OUT_DIR / "method3_arm_results.csv")
    print(f"  Loaded {len(df_arms)} results from 3 arms")

    # Load query targets for intensity_target
    df_targets = pd.read_csv(config.OUT_DIR / "query_targets.csv")

    # Load full song info for URLs
    df_songs = pd.read_csv(config.FULL_CATALOG_CSV)

    # Filter to top-3 only
    df_top3 = df_arms[df_arms["rank"] <= 3].copy()

    # Create union of (query_id, tag) pairs across all arms
    pairs = set()
    for _, row in df_top3.iterrows():
        pairs.add((row["query_id"], row["tag"]))

    print(f"\nUnion of top-3 pairs:")
    print(f"  Expected maximum: 3 arms × 8 queries × 3 ranks = 72 pairs")
    print(f"  Actual unique pairs: {len(pairs)}")

    # Build the full sheet
    rows_blind = []
    rows_mapping = []
    eval_id = 1

    for query_id, tag in sorted(pairs):
        # Find all arms that picked this pair
        arm_matches = df_top3[(df_top3["query_id"] == query_id) & (df_top3["tag"] == tag)]
        arms_str = "|".join(sorted(arm_matches["arm"].unique()))

        # Get song details
        song_row = df_songs[df_songs["tag"] == tag].iloc[0]
        band = song_row["band"]
        song = song_row["song"]
        url = song_row["url"]

        # Get query text
        query_spec = config.QUERIES[query_id]
        prompt_text = query_spec["text"]

        # Get target intensity
        target_row = df_targets[df_targets["query_id"] == query_id].iloc[0]
        intensity_target = target_row["intensity_target"]

        # Get acoustic features (we know they exist from arm results)
        first_arm = arm_matches.iloc[0]
        intensity = first_arm["intensity"]
        band_pct = first_arm["band_pct"]

        # Blind sheet (no identity columns)
        rows_blind.append({
            "eval_id": eval_id,
            "query_id": query_id,
            "prompt_text": prompt_text,
            "band": band,
            "song": song,
            "url": url,
            "score": "",  # To be filled by researcher
            "comment": "",  # To be filled by researcher
        })

        # Mapping sheet (for unblinding)
        rows_mapping.append({
            "eval_id": eval_id,
            "query_id": query_id,
            "tag": tag,
            "arms": arms_str,
            "intensity": intensity,
            "band_pct": band_pct,
            "intensity_target": intensity_target,
        })

        eval_id += 1

    # Shuffle using fixed seed (DESIGN.md §4b)
    rng = Random(config.SEED)
    indices = list(range(len(rows_blind)))
    rng.shuffle(indices)

    # Re-index both sheets with shuffled order
    rows_blind_shuffled = [rows_blind[i] for i in indices]
    rows_mapping_shuffled = [rows_mapping[i] for i in indices]

    # Update eval_id after shuffle
    for i, row in enumerate(rows_blind_shuffled, 1):
        row["eval_id"] = i
    for i, row in enumerate(rows_mapping_shuffled, 1):
        row["eval_id"] = i

    # Save both sheets
    blind_csv = config.OUT_DIR / "method3_blind_sheet.csv"
    mapping_csv = config.OUT_DIR / "method3_blind_mapping.csv"

    df_blind = pd.DataFrame(rows_blind_shuffled)
    df_mapping = pd.DataFrame(rows_mapping_shuffled)

    df_blind.to_csv(blind_csv, index=False, encoding="utf-8")
    df_mapping.to_csv(mapping_csv, index=False, encoding="utf-8")

    print(f"\n--- BLIND SHEET COMPLETE ---")
    print(f"Blind evaluation sheet: {blind_csv}")
    print(f"  {len(df_blind)} unique (query_id, tag) pairs")
    print(f"  Columns: eval_id, query_id, prompt_text, band, song, url, score (empty), comment (empty)")
    print(f"\nUnblinding mapping (DO NOT OPEN BEFORE EVALUATION): {mapping_csv}")
    print(f"  Columns: eval_id, query_id, tag, arms, intensity, band_pct, intensity_target")
    print(f"\n*** IMPORTANT: Ready for listening evaluation ***")
    print(f"*** Fill in 'score' (1-5 Likert) and optional 'comment' in {blind_csv} ***")


if __name__ == "__main__":
    main()
