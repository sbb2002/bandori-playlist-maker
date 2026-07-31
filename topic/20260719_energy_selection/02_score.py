"""
Step 2: Rule-based scoring of responses.

DESIGN.md §4: Calculate shape_match, peak_position_match, magnitude_sanity for each trial.

Output: out/scored.csv (columns: variant, query_id, trial, parse_success, shape_match,
         peak_position_match, magnitude_sanity, query_score)
"""
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np

import config
import queries

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def score_shape_match(resolved_energies, expected_shape):
    """Calculate shape_match score (DESIGN.md §4-2).

    Scores:
    - 1.0: Perfect match
    - 0.5: Approximate match
    - 0.0: No match
    """
    if len(resolved_energies) < 2:
        return 0.0

    diff = np.diff(resolved_energies)
    tolerance = 0.03

    if expected_shape == "flat":
        # max - min ≤ 0.15
        if max(resolved_energies) - min(resolved_energies) <= 0.15:
            return 1.0
        else:
            return 0.0

    elif expected_shape == "rising":
        # All diffs should be non-negative (rising)
        positive_count = np.sum(diff > -tolerance)
        total_count = len(diff)
        if positive_count == total_count:
            return 1.0
        elif positive_count / total_count >= 0.80:
            return 0.5
        else:
            return 0.0

    elif expected_shape == "falling":
        # All diffs should be non-positive (falling)
        negative_count = np.sum(diff < tolerance)
        total_count = len(diff)
        if negative_count == total_count:
            return 1.0
        elif negative_count / total_count >= 0.80:
            return 0.5
        else:
            return 0.0

    elif expected_shape == "peak":
        # Max should not be at start or end, with rises/falls on both sides
        max_idx = np.argmax(resolved_energies)
        N = len(resolved_energies)

        if max_idx == 0 or max_idx == N - 1:
            return 0.0  # Peak at edge = monotonic

        # Check if there's at least one rise before and one fall after
        has_rise_before = np.any(diff[:max_idx] > -tolerance)
        has_fall_after = np.any(diff[max_idx:] < tolerance)

        if has_rise_before and has_fall_after:
            return 1.0
        elif max_idx >= N - 2:  # Peak near end (2nd-to-last position or before)
            return 0.5
        else:
            return 0.5 if (has_rise_before or has_fall_after) else 0.0

    return 0.0


def score_peak_position_match(resolved_energies, peak_minute, target_minutes):
    """Calculate peak_position_match score for category B queries (DESIGN.md §4-3).

    Returns 0.0 if not applicable (non-B query).
    """
    if peak_minute is None or target_minutes is None:
        return 0.0

    expected_fraction = peak_minute / target_minutes
    max_idx = np.argmax(resolved_energies)
    N = len(resolved_energies)
    actual_fraction = max_idx / (N - 1) if N > 1 else 0.0

    abs_error = abs(expected_fraction - actual_fraction)

    if abs_error <= 0.20:
        return 1.0
    elif abs_error <= 0.35:
        return 0.5
    else:
        return 0.0


def score_magnitude_sanity(resolved_energies, magnitude_checks):
    """Check magnitude constraints (DESIGN.md §4-4).

    All checks must pass (AND logic).
    """
    if not magnitude_checks:
        return 1.0  # No constraints = pass

    for check_type, threshold in magnitude_checks.items():
        if check_type == "all_below":
            if not (max(resolved_energies) <= threshold):
                return 0.0
        elif check_type == "all_above":
            if not (min(resolved_energies) >= threshold):
                return 0.0
        elif check_type == "peak_above":
            if not (max(resolved_energies) >= threshold):
                return 0.0
        elif check_type == "first_below":
            if not (resolved_energies[0] <= threshold):
                return 0.0
        elif check_type == "end_above":
            if not (resolved_energies[-1] >= threshold):
                return 0.0
        elif check_type == "start_below":
            if not (resolved_energies[0] <= threshold):
                return 0.0
        elif check_type == "end_below":
            if not (resolved_energies[-1] <= threshold):
                return 0.0

    return 1.0


def score_responses(df_raw):
    """Score each trial based on rules.

    Input: out/raw_responses.csv
    Output: out/scored.csv
    """
    results = []

    for _, row in df_raw.iterrows():
        variant = row["variant"]
        query_id = row["query_id"]
        trial = int(row["trial"])
        parse_success = bool(row["parse_success"])

        # Fetch query spec
        if query_id not in queries.QUERIES:
            print(f"WARNING: Unknown query {query_id}, skip")
            continue

        query_spec = queries.QUERIES[query_id]
        expected_shape = query_spec["expected_shape"]
        category = query_spec["category"]
        peak_minute = query_spec["peak_minute"]
        target_minutes = query_spec["target_minutes"]
        magnitude_checks = query_spec["magnitude_checks"]

        if not parse_success:
            # Parse failure = all scores zero
            results.append({
                "variant": variant,
                "query_id": query_id,
                "trial": trial,
                "category": category,
                "parse_success": False,
                "shape_match": 0.0,
                "peak_position_match": 0.0,
                "magnitude_sanity": 0.0,
                "query_score": 0.0,
            })
            continue

        # Parse resolved_energies
        resolved_str = row["resolved_energies"]
        try:
            resolved_energies = json.loads(resolved_str)
        except (json.JSONDecodeError, TypeError):
            # Fallback: mark as parse failure
            results.append({
                "variant": variant,
                "query_id": query_id,
                "trial": trial,
                "category": category,
                "parse_success": False,
                "shape_match": 0.0,
                "peak_position_match": 0.0,
                "magnitude_sanity": 0.0,
                "query_score": 0.0,
            })
            continue

        resolved_energies = np.array(resolved_energies)

        # Calculate individual scores
        shape_match = score_shape_match(resolved_energies, expected_shape)
        peak_position_match = score_peak_position_match(resolved_energies, peak_minute, target_minutes)
        magnitude_sanity = score_magnitude_sanity(resolved_energies, magnitude_checks)

        # Aggregate score: average of applicable metrics
        applicable_scores = [shape_match, magnitude_sanity]
        if category == "B":  # Only B queries have peak_position_match
            applicable_scores.append(peak_position_match)

        query_score = np.mean(applicable_scores)

        results.append({
            "variant": variant,
            "query_id": query_id,
            "trial": trial,
            "category": category,
            "parse_success": True,
            "shape_match": shape_match,
            "peak_position_match": peak_position_match if category == "B" else np.nan,
            "magnitude_sanity": magnitude_sanity,
            "query_score": query_score,
        })

    return pd.DataFrame(results)


def main():
    raw_csv = config.OUT_DIR / "raw_responses.csv"
    scored_csv = config.OUT_DIR / "scored.csv"

    if not raw_csv.exists():
        print(f"ERROR: {raw_csv} not found. Run 01_run_variants.py first.")
        sys.exit(1)

    print("=== Step 2: Score responses ===")
    df_raw = pd.read_csv(raw_csv)
    df_scored = score_responses(df_raw)
    df_scored.to_csv(scored_csv, index=False, encoding="utf-8")

    print(f"\nScored {len(df_scored)} trials")
    print(f"Results saved to {scored_csv}")

    # Summary by variant × category
    print("\n--- Query Score by Variant × Category (mean) ---")
    pivot = df_scored.pivot_table(
        values="query_score",
        index="variant",
        columns="category",
        aggfunc="mean",
    )
    print(pivot.round(3))

    # Summary stats
    print("\n--- Overall Query Score by Variant (mean ± std) ---")
    summary = df_scored.groupby("variant")["query_score"].agg(["mean", "std"])
    print(summary.round(3))


if __name__ == "__main__":
    main()
