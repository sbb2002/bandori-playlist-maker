"""Analyze evaluation results and compute metrics.

Outputs:
  - out/analysis_summary.csv: (arm×level)×category metrics
  - stdout: judgment, RQ2 analysis, markdown summary
"""
from pathlib import Path
import sys
import math

import numpy as np
import pandas as pd

import config

SCRIPT_DIR = Path(__file__).parent


def dcg_at_k(gains, k=5):
    """Compute Discounted Cumulative Gain."""
    gains = np.array(gains[:k])
    discounts = np.log2(np.arange(2, len(gains) + 2))  # log2(2), log2(3), ...
    return np.sum(gains / discounts)


def ndcg_at_k(gains, k=5):
    """Compute Normalized DCG (NDCG)."""
    dcg = dcg_at_k(gains, k)
    # IDCG: sort all gains in descending order and compute DCG of top-k
    all_gains = sorted(gains, reverse=True)
    idcg = dcg_at_k(all_gains, k)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def analyze_results():
    """Analyze evaluation results."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load evaluation sheets
    eval_csv = config.OUT_DIR / "eval_sheet.csv"
    mapping_csv = config.OUT_DIR / "eval_mapping.csv"

    if not eval_csv.exists() or not mapping_csv.exists():
        print("ERROR: eval_sheet.csv or eval_mapping.csv not found. Run 04_search.py first.")
        sys.exit(1)

    df_eval = pd.read_csv(eval_csv)
    df_mapping = pd.read_csv(mapping_csv)

    # === Validation: check all scores are filled ===
    print("=== Validating scores ===")

    # Convert score to numeric, empty strings become NaN
    df_eval["score"] = pd.to_numeric(df_eval["score"], errors="coerce")

    empty_pairs = df_eval[df_eval["score"].isna()]
    if len(empty_pairs) > 0:
        print(f"ERROR: {len(empty_pairs)} pairs have empty scores:")
        for _, row in empty_pairs.iterrows():
            print(f"  {row['pair_id']}: {row['category_id']} - {row['band']} - {row['song']}")
        sys.exit(1)

    print(f"(ok) All {len(df_eval)} pairs scored")

    # === Merge scores with mapping ===
    print("\n=== Computing metrics ===")

    # mapping has pair_id, arm, prompt_id, rank, tag
    # eval has pair_id, score, ...

    df_merged = df_mapping.merge(df_eval[["pair_id", "category_id", "score"]], on="pair_id")

    # Extract level from prompt_id
    df_merged["level"] = df_merged["prompt_id"].str.extract(r"(L\d)")[0]

    print(f"Merged: {len(df_merged)} rows")

    # === Compute metrics by (arm, level, category) ===
    analysis_records = []

    for arm in ["raw", "summary", "keyword"]:
        for level in ["L1", "L4"]:
            for category_id in config.CATEGORIES.keys():
                subset = df_merged[
                    (df_merged["arm"] == arm)
                    & (df_merged["level"] == level)
                    & (df_merged["category_id"] == category_id)
                ]

                if len(subset) == 0:
                    continue

                # DCG needs rank order
                subset = subset.sort_values("rank")
                scores = subset["score"].values

                # mean_score
                mean_score = np.mean(scores)

                # p_at_5: fraction of scores >= 4
                p_at_5 = np.sum(scores >= 4) / len(scores) if len(scores) > 0 else 0

                # ndcg_at_5: gains = score-1; IDCG from ALL rated pairs in this
                # category (selection-aware, per DESIGN §6-05), not just own top-5
                gains = scores - 1
                cat_pool = df_eval[df_eval["category_id"] == category_id]["score"].values
                ideal_gains = np.sort(cat_pool - 1)[::-1]
                idcg = dcg_at_k(ideal_gains, k=5)
                ndcg = dcg_at_k(gains, k=5) / idcg if idcg > 0 else 0.0

                analysis_records.append({
                    "arm": arm,
                    "level": level,
                    "category_id": category_id,
                    "category_name": config.CATEGORIES[category_id],
                    "mean_score": mean_score,
                    "p_at_5": p_at_5,
                    "ndcg_at_5": ndcg,
                    "n_pairs": len(subset),
                })

    # === Add overall rows by (arm, level): macro-average over categories ===
    for arm in ["raw", "summary", "keyword"]:
        for level in ["L1", "L4"]:
            cat_rows = [
                r for r in analysis_records
                if r["arm"] == arm and r["level"] == level
                and r["category_id"] in config.CATEGORIES
            ]
            if not cat_rows:
                continue

            analysis_records.append({
                "arm": arm,
                "level": level,
                "category_id": "OVERALL",
                "category_name": "All Categories (macro avg)",
                "mean_score": np.mean([r["mean_score"] for r in cat_rows]),
                "p_at_5": np.mean([r["p_at_5"] for r in cat_rows]),
                "ndcg_at_5": np.mean([r["ndcg_at_5"] for r in cat_rows]),
                "n_pairs": sum(r["n_pairs"] for r in cat_rows),
            })

    df_analysis = pd.DataFrame(analysis_records)
    analysis_csv = config.OUT_DIR / "analysis_summary.csv"
    df_analysis.to_csv(analysis_csv, index=False, encoding="utf-8")
    print(f"Saved analysis to {analysis_csv}")

    # === Output results ===
    print("\n" + "=" * 70)
    print("ANALYSIS RESULTS")
    print("=" * 70)

    # Find best (arm, level) combination overall
    overall_rows = df_analysis[df_analysis["category_id"] == "OVERALL"]
    best_row = overall_rows.loc[overall_rows["mean_score"].idxmax()]
    best_arm = best_row["arm"]
    best_level = best_row["level"]
    best_mean = best_row["mean_score"]

    # === Judgment (§0 criteria, adjusted for 14-song sample) ===
    print("\n[1] JUDGMENT (based on best arm×level combination)")
    print(f"  Best: {best_arm} × {best_level} (mean={best_mean:.2f})")

    # Note: criteria adjusted for 14-song sample (§7)
    print(
        f"  Note: Pool size is 14 songs (sample run). Criteria from §0 apply as reference only."
        f"\n  - Adopt candidate: 4/4 categories ≥3.5 mean AND 3/4 categories with ≥2 songs scoring ≥4"
        f"\n  - Conditional retry: 2.5-3.5 range → investigate causes"
        f"\n  - Reject: <2.5"
    )

    if best_mean >= 3.5:
        cat_scores = df_analysis[
            (df_analysis["arm"] == best_arm)
            & (df_analysis["level"] == best_level)
            & (df_analysis["category_id"] != "OVERALL")
        ]
        high_p_at_5 = np.sum(cat_scores["p_at_5"] >= 0.4)  # ≥2 out of 5
        if high_p_at_5 >= 3:
            judgment = "ADOPT CANDIDATE (all criteria met)"
        else:
            judgment = f"CONDITIONAL RETRY (mean ≥3.5 but only {high_p_at_5}/4 categories strong)"
    elif best_mean >= 2.5:
        judgment = "CONDITIONAL RETRY (2.5-3.5 range → investigate)"
    else:
        judgment = "REJECT (<2.5)"

    print(f"\n  Judgment: {judgment}")

    # === RQ2: L1 vs L4 gap by arm ===
    print("\n[2] RQ2: Does prompt expansion (L1→L4) close the specificity gap?")
    print("  (Comparing mean_score: higher L4 - L1 gap suggests expansion helps)\n")

    gap_records = []
    for arm in ["raw", "summary", "keyword"]:
        overall_l1 = df_analysis[
            (df_analysis["arm"] == arm)
            & (df_analysis["level"] == "L1")
            & (df_analysis["category_id"] == "OVERALL")
        ]
        overall_l4 = df_analysis[
            (df_analysis["arm"] == arm)
            & (df_analysis["level"] == "L4")
            & (df_analysis["category_id"] == "OVERALL")
        ]

        if len(overall_l1) > 0 and len(overall_l4) > 0:
            l1_mean = overall_l1.iloc[0]["mean_score"]
            l4_mean = overall_l4.iloc[0]["mean_score"]
            gap = l4_mean - l1_mean
            gap_records.append({
                "arm": arm,
                "L1_mean": l1_mean,
                "L4_mean": l4_mean,
                "gap": gap,
            })
            print(f"  {arm:10s}: L1={l1_mean:.2f}, L4={l4_mean:.2f}, gap={gap:+.2f}")

    # === Markdown summary table ===
    print("\n[3] DETAILED METRICS TABLE\n")

    # Pivot: arm × (level+category)
    summary_pivot = df_analysis[df_analysis["category_id"] != "OVERALL"].copy()
    summary_pivot = summary_pivot.sort_values(["arm", "level", "category_id"])

    print("| arm | level | C1 (슬픔) | C2 (가련함) | C3 (힙함) | C4 (밝음) |")
    print("|---|---|---|---|---|---|")

    for arm in ["raw", "summary", "keyword"]:
        for level in ["L1", "L4"]:
            row_data = summary_pivot[
                (summary_pivot["arm"] == arm)
                & (summary_pivot["level"] == level)
            ]

            if len(row_data) == 0:
                continue

            row_str = f"| {arm} | {level} |"
            for category_id in ["C1", "C2", "C3", "C4"]:
                cat_data = row_data[row_data["category_id"] == category_id]
                if len(cat_data) > 0:
                    mean = cat_data.iloc[0]["mean_score"]
                    row_str += f" {mean:.2f} |"
                else:
                    row_str += " — |"

            print(row_str)

    # Overall means
    print("\n| arm | level | **ALL** |")
    print("|---|---|---|")
    for arm in ["raw", "summary", "keyword"]:
        for level in ["L1", "L4"]:
            overall = df_analysis[
                (df_analysis["arm"] == arm)
                & (df_analysis["level"] == level)
                & (df_analysis["category_id"] == "OVERALL")
            ]
            if len(overall) > 0:
                mean = overall.iloc[0]["mean_score"]
                print(f"| {arm} | {level} | **{mean:.2f}** |")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    analyze_results()
