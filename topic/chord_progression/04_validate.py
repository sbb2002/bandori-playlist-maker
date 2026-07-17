"""Validate chord features against ground truth labels.

DESIGN.md §5:
1. Compute bright-vs-dark separation (mean diff + Cohen's d) for each feature
2. Compare against mode_score baseline
3. Check if 3 known mismatches are repositioned toward "bright"
Output: out/pilot_validation.csv, out/pilot_mismatch_check.csv
"""
import pandas as pd
import numpy as np
from scipy import stats

from config import OUT_DIR, SONGS_MASTER


def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """
    Compute Cohen's d effect size.

    Args:
        group1, group2: Two groups of values

    Returns:
        Cohen's d
    """
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

    if n1 + n2 - 2 == 0:
        return 0.0

    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    if pooled_std == 0:
        return 0.0

    return (np.mean(group1) - np.mean(group2)) / pooled_std


def percentile_in_group(value: float, group: np.ndarray) -> float:
    """
    Compute percentile rank of value within group (0-100).
    """
    if len(group) == 0:
        return 0.0
    return 100.0 * np.sum(group <= value) / len(group)


def main():
    # Load feature data
    features_path = OUT_DIR / "chord_features.csv"
    if not features_path.exists():
        raise FileNotFoundError("Chord features not found. Run 03_compute_features.py first.")

    features_df = pd.read_csv(features_path)
    print(f"Loaded {len(features_df)} feature records")

    # Load pilot song list
    pilot_path = OUT_DIR / "pilot_song_list.csv"
    if not pilot_path.exists():
        raise FileNotFoundError("Pilot song list not found")

    pilot_df = pd.read_csv(pilot_path)

    # Merge features with labels
    data = pilot_df.merge(features_df, on="tag", how="left")
    print(f"Merged data: {len(data)} rows")

    # Load mode_score from songs_master for baseline
    songs_master_df = pd.read_csv(SONGS_MASTER)
    # Match by idx (songs_master idx)
    mode_scores = {}
    for idx, row in songs_master_df.iterrows():
        mode_scores[(row["band"], row["song"])] = row["mode_score"]

    data["mode_score"] = data.apply(
        lambda row: mode_scores.get((row["band"], row["song"]), np.nan),
        axis=1
    )

    print("\nData with labels and features:")
    print(data[["tag", "band", "song", "label", "pct_major", "chord_change_rate", "borrowed_chord_rate", "mode_score"]])

    # ========================================================================
    # Validation: bright vs dark separation
    # ========================================================================

    bright_data = data[data["label"] == "Bright"]
    dark_data = data[data["label"] == "Dark"]

    features_to_eval = [
        "pct_major",
        "chord_change_rate",
        "borrowed_chord_rate",
        "mode_score",
    ]

    validation_rows = []
    for feature in features_to_eval:
        bright_vals = bright_data[feature].dropna().values
        dark_vals = dark_data[feature].dropna().values

        if len(bright_vals) > 0 and len(dark_vals) > 0:
            bright_mean = float(np.mean(bright_vals))
            dark_mean = float(np.mean(dark_vals))
            d = float(cohens_d(bright_vals, dark_vals))

            validation_rows.append({
                "feature": feature,
                "bright_mean": bright_mean,
                "dark_mean": dark_mean,
                "cohens_d": d,
            })
            print(f"\n{feature}:")
            print(f"  Bright: mean={bright_mean:.4f}, n={len(bright_vals)}")
            print(f"  Dark:   mean={dark_mean:.4f}, n={len(dark_vals)}")
            print(f"  Cohen's d: {d:.4f}")

    validation_df = pd.DataFrame(validation_rows)
    validation_path = OUT_DIR / "pilot_validation.csv"
    validation_df.to_csv(validation_path, index=False)
    print(f"\nSaved validation results to {validation_path}")

    # ========================================================================
    # Mismatch check: where do the 3 known mismatches rank?
    # ========================================================================

    mismatch_data = data[data["label"] == "mismatch_known"].copy()

    if len(mismatch_data) > 0:
        # BUGFIX (DESIGN.md §5 step 2): "각 지표의 백분위(19곡 또는 전체 661곡
        # 대비, 둘 다 기록)" explicitly requires recording percentiles against
        # BOTH the 19-song pilot pool and the full 661-song catalog. The
        # original code only ever computed the percentile within `data`
        # (the 19-song pilot pool) and never touched the 661-song population.
        #
        # For mode_score, the full-catalog value already exists for all 661
        # songs in songs_master.csv, so we can compute both here. For the 3
        # chord-derived features (pct_major, chord_change_rate,
        # borrowed_chord_rate), chord extraction was only run on the 19 pilot
        # songs (per DESIGN.md §2 scope) — a genuine 661-song percentile is
        # not computable without running 02/03 over the full catalog, which
        # is explicitly out of scope for this pilot (§0: "본격 661곡 확장
        # 전에... 싸게 먼저 본다"). Those columns are left NaN with a note,
        # rather than silently omitted, so the gap is visible in the CSV.
        mode_score_all_661 = songs_master_df["mode_score"].dropna().values

        # Flatten the mismatch data into one row per song
        mismatch_summary = []
        for idx, row in mismatch_data.iterrows():
            summary = {
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
            }
            for feature in features_to_eval:
                all_vals = data[feature].dropna().values
                feature_val = row[feature]
                if pd.notna(feature_val):
                    pct_19 = percentile_in_group(feature_val, all_vals)
                else:
                    pct_19 = np.nan
                summary[f"{feature}_pct"] = pct_19  # 19-song pilot pool basis

                if feature == "mode_score" and pd.notna(feature_val):
                    summary[f"{feature}_pct_661"] = percentile_in_group(
                        feature_val, mode_score_all_661
                    )
                else:
                    # Not computable at pilot scope (see note above) for the
                    # 3 chord-derived candidate features.
                    summary[f"{feature}_pct_661"] = np.nan

            mismatch_summary.append(summary)

        mismatch_df = pd.DataFrame(mismatch_summary)
        mismatch_path = OUT_DIR / "pilot_mismatch_check.csv"
        mismatch_df.to_csv(mismatch_path, index=False)
        print(f"\nSaved mismatch percentile check to {mismatch_path}")
        print("\nKnown mismatches percentile rank (0=lowest, 100=highest):")
        print(mismatch_df.to_string(index=False))

        # Summary interpretation
        print("\n=== MISMATCH INTERPRETATION ===")
        for idx, row in mismatch_df.iterrows():
            tag = row["tag"]
            song_title = f"{row['band']} / {row['song']}"
            print(f"\n{song_title}:")

            # Check if moved toward "bright" (high percentile in chord features)
            pct_major_pct = row["pct_major_pct"]
            chord_change_pct = row["chord_change_rate_pct"]
            borrowed_chord_pct = row["borrowed_chord_rate_pct"]
            mode_score_pct = row["mode_score_pct"]
            mode_score_pct_661 = row["mode_score_pct_661"]

            print(f"  pct_major: {pct_major_pct:.1f}th percentile (of 19)")
            print(f"  chord_change_rate: {chord_change_pct:.1f}th percentile (of 19)")
            print(f"  borrowed_chord_rate: {borrowed_chord_pct:.1f}th percentile (of 19)")
            print(f"  mode_score (baseline): {mode_score_pct:.1f}th percentile (of 19)"
                  f" / {mode_score_pct_661:.1f}th percentile (of 661, DESIGN.md §0 reference)")

            # Interpretation
            if mode_score_pct < 25:
                print(f"  ⚠️  mode_score is very dark (< 25th percentile)")
            if pct_major_pct > 75 or chord_change_pct > 75 or borrowed_chord_pct > 75:
                print(f"  ✓ At least one chord feature is bright (> 75th percentile) — possible improvement")
            else:
                print(f"  ✗ No chord feature shows strong brightness signal")
    else:
        print("\nNo known mismatches found in data")


if __name__ == "__main__":
    main()
