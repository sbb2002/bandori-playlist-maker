"""
Step 3: Compare variants using Wilcoxon signed-rank test.

DESIGN.md §2, §4: Pairwise comparison (baseline vs candidates), decision table application.

Output: out/comparison_summary.csv (variant, category, mean_score, std)
        + console report with Wilcoxon p-values and final decision
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from scipy import stats

import config
import queries

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def aggregate_to_query_level(df_scored):
    """Aggregate trials to query level (mean of 5 trials per query-variant pair).

    Returns DataFrame with columns: variant, query_id, category, query_score
    """
    agg = df_scored.groupby(["variant", "query_id"])["query_score"].agg(["mean", "std", "count"]).reset_index()
    agg.columns = ["variant", "query_id", "mean_score", "std_score", "n_trials"]

    # Add category back
    category_map = {qid: queries.QUERIES[qid]["category"] for qid in queries.QUERIES}
    agg["category"] = agg["query_id"].map(category_map)

    return agg[["variant", "query_id", "category", "mean_score", "std_score", "n_trials"]]


def wilcoxon_compare(baseline_scores, candidate_scores):
    """Wilcoxon signed-rank test: baseline vs candidate (paired, query-level).

    Returns: (p_value, mean_diff, effect_size_approx)
    """
    if len(baseline_scores) != len(candidate_scores) or len(baseline_scores) == 0:
        return np.nan, np.nan, np.nan

    diff = candidate_scores - baseline_scores
    try:
        stat, p_value = stats.wilcoxon(diff, alternative="two-sided")
    except ValueError:
        # All diffs zero (or too few non-zero pairs) — wilcoxon undefined, treat as no difference.
        p_value = 1.0

    mean_diff = np.mean(diff)
    # Rough effect size (mean diff / pooled std)
    pooled_std = np.std(np.concatenate([baseline_scores, candidate_scores]))
    effect_size = mean_diff / pooled_std if pooled_std > 0 else 0.0

    return p_value, mean_diff, effect_size


# candidate -> (primary categories = 실패모드, regression categories = 회귀방지)
# DESIGN.md §2 (candidate_A/B/AB) + §9 (candidate_E, Phase 2)
CANDIDATE_CATEGORY_MAP = {
    "candidate_A": (["A", "B"], ["C", "D"]),
    "candidate_B": (["A", "B"], ["C", "D"]),
    "candidate_AB": (["A", "B"], ["C", "D"]),
    "candidate_E": (["E", "F"], ["A", "B", "C", "D"]),
}


def apply_decision_table(primary_wilcoxon_p, primary_mean_diff, regression_ok):
    """Apply DESIGN.md §2/§9 decision table.

    Args:
        primary_wilcoxon_p: Wilcoxon p-value for primary (실패모드) queries (lower is better)
        primary_mean_diff: Mean score difference (candidate - baseline) for primary queries
        regression_ok: bool, whether regression-category score difference ≥ -0.05

    Returns:
        decision: "채택" | "부분채택" | "기각"
    """
    # Criteria for primary improvement:
    # - Wilcoxon p < 0.05, OR
    # - Direction consistent (mean_diff > 0)
    primary_improved = (
        primary_wilcoxon_p < 0.05 if not np.isnan(primary_wilcoxon_p) else False
    ) or primary_mean_diff > 0.0

    if primary_improved and regression_ok:
        return "채택"
    elif primary_improved and not regression_ok:
        return "부분채택"
    else:
        return "기각"


def compare_variants(df_query_level):
    """Run pairwise comparisons (baseline vs each candidate in CANDIDATE_CATEGORY_MAP).

    Returns summary DataFrame and decision text.
    """
    present_variants = set(df_query_level["variant"].unique())
    candidates = [c for c in CANDIDATE_CATEGORY_MAP if c in present_variants]
    summary_rows = []

    print("\n--- Wilcoxon Signed-Rank Tests (per-candidate primary vs regression categories) ---")

    for candidate in candidates:
        primary_cats, regression_cats = CANDIDATE_CATEGORY_MAP[candidate]
        print(f"\n{candidate} vs baseline (primary={'+'.join(primary_cats)}, regression={'+'.join(regression_cats)}):")

        # Extract scores by query
        df_baseline = df_query_level[df_query_level["variant"] == "baseline"].copy()
        df_cand = df_query_level[df_query_level["variant"] == candidate].copy()

        # Ensure aligned by query_id
        common_queries = sorted(set(df_baseline["query_id"]) & set(df_cand["query_id"]))

        # primary: 실패모드 카테고리
        primary_queries = [q for q in common_queries if queries.QUERIES[q]["category"] in primary_cats]
        baseline_primary = df_baseline.set_index("query_id").loc[primary_queries, "mean_score"].values
        cand_primary = df_cand.set_index("query_id").loc[primary_queries, "mean_score"].values

        # regression: 회귀방지 카테고리
        regression_queries = [q for q in common_queries if queries.QUERIES[q]["category"] in regression_cats]
        baseline_reg = df_baseline.set_index("query_id").loc[regression_queries, "mean_score"].values
        cand_reg = df_cand.set_index("query_id").loc[regression_queries, "mean_score"].values

        # Wilcoxon for primary
        p_primary, mean_diff_primary, effect_primary = wilcoxon_compare(baseline_primary, cand_primary)
        baseline_reg_mean = np.mean(baseline_reg) if len(baseline_reg) > 0 else np.nan
        cand_reg_mean = np.mean(cand_reg) if len(cand_reg) > 0 else np.nan
        reg_diff = cand_reg_mean - baseline_reg_mean
        regression_ok = reg_diff >= -0.05

        p_primary_str = f"{p_primary:.4f}" if not np.isnan(p_primary) else "nan"
        print(f"  primary (n={len(primary_queries)}): baseline={np.mean(baseline_primary):.3f}, "
              f"candidate={np.mean(cand_primary):.3f}, p={p_primary_str}, "
              f"diff={mean_diff_primary:.3f}")
        print(f"  regression (n={len(regression_queries)}): baseline={baseline_reg_mean:.3f}, "
              f"candidate={cand_reg_mean:.3f}, diff={reg_diff:.3f} (ok={regression_ok})")

        # Decision
        decision = apply_decision_table(p_primary, mean_diff_primary, regression_ok)
        print(f"  Decision: {decision}")

        summary_rows.append({
            "variant": candidate,
            "primary_categories": "+".join(primary_cats),
            "regression_categories": "+".join(regression_cats),
            "primary_wilcoxon_p": p_primary,
            "primary_mean_diff": mean_diff_primary,
            "primary_effect_size": effect_primary,
            "regression_mean_baseline": baseline_reg_mean,
            "regression_mean_candidate": cand_reg_mean,
            "regression_ok": regression_ok,
            "decision": decision,
        })

    return pd.DataFrame(summary_rows)


def main():
    scored_csv = config.OUT_DIR / "scored.csv"
    comparison_csv = config.OUT_DIR / "comparison_summary.csv"

    if not scored_csv.exists():
        print(f"ERROR: {scored_csv} not found. Run 02_score.py first.")
        sys.exit(1)

    print("=== Step 3: Compare variants ===")
    df_scored = pd.read_csv(scored_csv)

    # Aggregate to query level
    df_query_level = aggregate_to_query_level(df_scored)

    print(f"\nQuery-level aggregation: {len(df_query_level)} rows (variants × queries)")

    # Pairwise comparison
    df_comparison = compare_variants(df_query_level)

    # Save summary
    df_comparison.to_csv(comparison_csv, index=False, encoding="utf-8")

    # Print final decision
    print("\n" + "="*60)
    print("FINAL DECISION (DESIGN.md §2)")
    print("="*60)
    for _, row in df_comparison.iterrows():
        variant = row["variant"]
        decision = row["decision"]
        print(f"{variant:15} → {decision}")

    print(f"\nComparison summary saved to {comparison_csv}")


if __name__ == "__main__":
    main()
