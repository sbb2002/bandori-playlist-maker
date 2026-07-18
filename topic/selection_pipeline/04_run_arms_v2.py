"""
Step 4: Run two arms (arm1 and arm2) and extract top-K results per query.

DESIGN_v2.md §0, §3: Arm 1 (production), Arm 2 (lyrics+intensity).
Arm 3 is excluded in v2 (see DESIGN_v2.md §0 rationale).
Each arm produces top-K=3 results per query.

Output: out/method3_arm_results_v2.csv
  Columns: query_id, arm, rank, tag, band, song, intensity, band_pct, lyric_cosine
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import config_v2 as config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_data():
    """Load all required input files.

    NOTE: df_ref (one row per song, 661 rows) is kept free of any
    query-specific join. query_lyric_candidates.csv is long-format
    (multiple query_id rows per tag, since a song can be a lyric
    candidate for several queries) — merging it directly onto df_ref
    on "tag" alone would duplicate a song's row once per query it is
    a candidate for, corrupting the band-filtered `eligible` pool that
    arm1 uses (which must have exactly one row per song and must not
    depend on lyric candidacy at all). df_candidates is therefore kept
    separate and joined per-query, per-arm in main() instead.
    """
    print("Loading input data...")
    df_targets = pd.read_csv(config.OUT_DIR / "query_targets_v2.csv")
    df_band_pct = pd.read_csv(config.OUT_DIR / "song_band_percentiles.csv")
    df_acoustics = pd.read_csv(config.SONG_ACOUSTICS_CSV)
    df_candidates = pd.read_csv(config.OUT_DIR / "query_lyric_candidates_v2.csv")
    df_songs = pd.read_csv(config.FULL_CATALOG_CSV)

    # Join acoustic features and band_pct into a single reference table,
    # one row per song (no query-specific duplication).
    df_ref = df_songs.copy()
    df_ref = df_ref.merge(df_acoustics[["tag", "intensity"]], on="tag", how="left")
    df_ref = df_ref.merge(df_band_pct[["tag", "band_pct"]], on="tag", how="left")

    print(f"  Loaded {len(df_targets)} queries")
    print(f"  Loaded {len(df_ref)} songs with features")
    assert len(df_ref) == len(df_songs), (
        "df_ref must have exactly one row per song; got "
        f"{len(df_ref)} vs {len(df_songs)}"
    )
    return df_targets, df_ref, df_candidates


def run_arm1(eligible_songs, intensity_target):
    """
    Arm 1: Production method (intensity only, no lyrics).

    Algorithm:
      window = songs where |intensity - intensity_target| <= 0.08
      if len(window) >= K:
          candidates = window sorted by intensity proximity
      else:
          candidates = all songs sorted by intensity proximity (fallback)
      return top-K
    """
    if pd.isna(intensity_target):
        # No intensity target -> return all eligible sorted by intensity
        return eligible_songs.sort_values("intensity", ascending=False).head(config.K)

    # Create window
    window = eligible_songs[
        np.abs(eligible_songs["intensity"] - intensity_target) <= config.TOL
    ]

    if len(window) >= config.K:
        # Window has enough songs -> sort by intensity proximity
        window = window.copy()
        window["_dist_to_target"] = np.abs(window["intensity"] - intensity_target)
        candidates = window.sort_values("_dist_to_target")
    else:
        # Fallback to all eligible, sorted by intensity proximity
        candidates = eligible_songs.copy()
        candidates["_dist_to_target"] = np.abs(candidates["intensity"] - intensity_target)
        candidates = candidates.sort_values("_dist_to_target")

    return candidates.head(config.K)


def run_arm2(candidate_pool, intensity_target):
    """
    Arm 2: Lyrics screening + absolute intensity.

    Algorithm: Same as Arm 1 but using candidate_pool instead of eligible_pool.
    """
    if pd.isna(intensity_target):
        # No intensity target -> return top of pool by lyric cosine
        return candidate_pool.head(config.K)

    # Create window
    window = candidate_pool[
        np.abs(candidate_pool["intensity"] - intensity_target) <= config.TOL
    ]

    if len(window) >= config.K:
        # Window has enough songs -> sort by intensity proximity
        window = window.copy()
        window["_dist_to_target"] = np.abs(window["intensity"] - intensity_target)
        candidates = window.sort_values("_dist_to_target")
    else:
        # Fallback to all in pool, sorted by intensity proximity
        candidates = candidate_pool.copy()
        candidates["_dist_to_target"] = np.abs(candidates["intensity"] - intensity_target)
        candidates = candidates.sort_values("_dist_to_target")

    return candidates.head(config.K)


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if output already exists
    output_csv = config.OUT_DIR / "method3_arm_results_v2.csv"
    if output_csv.exists():
        print(f"Output already exists: {output_csv}")
        df_results = pd.read_csv(output_csv)
        print(f"Loaded {len(df_results)} rows")
        return

    df_targets, df_ref, df_candidates = load_data()

    results = []

    print("\nRunning arms (v2: arm1 + arm2 only)...")
    for _, target_row in df_targets.iterrows():
        query_id = target_row["query_id"]
        intensity_target = target_row["intensity_target"]
        band_filter = target_row["band_filter"]

        # Define eligible_pool (band_filter applied first)
        if pd.notna(band_filter) and band_filter:
            eligible = df_ref[df_ref["band"] == band_filter]
        else:
            eligible = df_ref

        print(f"\n  Query {query_id} (target intensity={intensity_target}, band={band_filter or 'NA'})")
        print(f"    Eligible pool size: {len(eligible)}")

        # Arm 1: No lyrics
        arm1_results = run_arm1(eligible.copy(), intensity_target)
        for rank, (_, row) in enumerate(arm1_results.iterrows(), 1):
            results.append({
                "query_id": query_id,
                "arm": "arm1",
                "rank": rank,
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
                "intensity": round(row["intensity"], 4),
                "band_pct": round(row["band_pct"], 4),
                "lyric_cosine": None,  # Arm 1 doesn't use lyrics
            })
        print(f"    Arm1 top-{min(3, len(arm1_results))}: {arm1_results['tag'].tolist()}")

        # Arm 2: candidate_pool = eligible songs that are lyric candidates
        # for this specific query. df_candidates is long-format (one row per
        # (query_id, tag)) so it must be filtered to this query_id BEFORE
        # joining onto eligible, otherwise the join would duplicate rows for
        # songs that are candidates in more than one query (see load_data()).
        query_N = config.compute_candidate_pool_size(len(eligible))
        cand_rows_for_query = df_candidates[
            (df_candidates["query_id"] == query_id) & (df_candidates["rank_in_pool"] <= query_N)
        ][["tag", "lyric_cosine", "rank_in_pool"]]
        df_candidates_for_query = eligible.merge(cand_rows_for_query, on="tag", how="inner")
        if len(df_candidates_for_query) > 0:
            arm2_results = run_arm2(df_candidates_for_query.copy(), intensity_target)
            for rank, (_, row) in enumerate(arm2_results.iterrows(), 1):
                results.append({
                    "query_id": query_id,
                    "arm": "arm2",
                    "rank": rank,
                    "tag": row["tag"],
                    "band": row["band"],
                    "song": row["song"],
                    "intensity": round(row["intensity"], 4),
                    "band_pct": round(row["band_pct"], 4),
                    "lyric_cosine": round(row["lyric_cosine"], 4),
                })
            print(f"    Arm2 top-{min(3, len(arm2_results))}: {arm2_results['tag'].tolist()}")
        else:
            print(f"    Arm2 skipped (no candidates)")

    # Save results
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df_results)} rows to {output_csv}")
    print(f"\n{df_results.groupby('arm').size()}")


if __name__ == "__main__":
    main()
