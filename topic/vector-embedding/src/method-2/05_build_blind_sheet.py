"""Stage 4: Build blind evaluation sheet — DESIGN.md §5.

Combines results from arms A/B/C and creates:
1. Blind sheet (arm/rank/score columns removed)
2. Unmask mapping (for post-evaluation analysis)

Rules:
  - Merge (query_id, tag) pairs from all arms (max 54 pairs: 6 queries × 3 ranks × 3 arms)
  - 47쌍 전량을 블라인드 재채점 대상으로 한다. method-1 점수를 승계하지 않는다(§5 정정).
  - 전 쌍을 함께 셔플(seed 20260717) — 일부만 섞으면 eval_id 순서가 arm을 누출한다.
  - Remove arm/rank/cosine from blind sheet; score/comment는 전 행 공란

Output:
  - out/phase2_blind_sheet.csv: eval_id, query_id, prompt_text, band, song, url,
    score (empty), comment (empty)
  - out/phase2_blind_mapping.csv: eval_id, query_id, tag, arms, rank_A, rank_B, rank_C,
    lyr_rank, acou_rank, acou_match (unlabeled, do not open until after scoring)
"""
import random
import sys
from pathlib import Path

import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build_blind_sheet():
    """Build blind evaluation sheet."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load search results
    results_csv = config.OUT_DIR / "phase2_search_results.csv"
    if not results_csv.exists():
        print(f"ERROR: {results_csv} not found. Run 04_fusion_search.py first.")
        sys.exit(1)

    df_results = pd.read_csv(results_csv)
    print(f"Loaded {len(df_results)} search results")

    # Load method-1 evaluation sheet for already-scored pairs
    m1_eval_csv = config.METHOD_1_OUT_DIR / "stage2_eval_sheet.csv"
    if not m1_eval_csv.exists():
        print(f"WARNING: {m1_eval_csv} not found, creating new evaluation")
        df_m1_eval = pd.DataFrame()
    else:
        df_m1_eval = pd.read_csv(m1_eval_csv)
        print(f"Loaded {len(df_m1_eval)} already-scored pairs from method-1")

    # Load catalog for URLs
    df_catalog = pd.read_csv(config.SONGS_CSV)
    url_map = dict(zip(df_catalog["tag"], df_catalog["url"]))

    # ========================================================================
    # Step 1: Collect all (query_id, tag) pairs from all arms
    # ========================================================================
    pairs_set = set()
    pair_details = {}

    for _, row in df_results.iterrows():
        query_id = row["query_id"]
        tag = row["tag"]
        pair = (query_id, tag)

        if pair not in pairs_set:
            pairs_set.add(pair)
            pair_details[pair] = {
                "query_id": query_id,
                "tag": tag,
                "band": row["band"],
                "song": row["song"],
                "url": row["url"],
                "arms": [],
                "ranks": {"A": None, "B": None, "C": None},
                "lyr_rank": None,
                "acou_rank": None,
                "acou_match": None,
            }

        # Track which arms have this pair and at what rank
        arm = row["arm"]
        rank = row["rank"]
        pair_details[pair]["arms"].append(arm)
        pair_details[pair]["ranks"][arm] = rank
        pair_details[pair]["lyr_rank"] = row["lyr_rank"]
        pair_details[pair]["acou_rank"] = row["acou_rank"]
        pair_details[pair]["acou_match"] = row["acou_match"]

    print(f"\nCollected {len(pairs_set)} unique (query_id, tag) pairs from all arms")

    # ========================================================================
    # Step 2: 전 쌍을 채점 대상으로 한다 — DESIGN.md §5 (2026-07-17 정정)
    # ========================================================================
    # 초안은 method-1에서 이미 채점된 쌍을 제외하고 점수를 승계하려 했으나 폐기됐다.
    # arm A의 쌍 = method-1의 쌍과 정확히 일치하고 A∩B=0이므로, 승계하면 arm A만
    # 비블라인드 점수가 되어 arm과 채점 조건이 교락된다. 47쌍 전부 블라인드 재채점한다.
    # method-1 점수는 승계하지 않고 재검사 신뢰도 계산에만 쓴다(원본 CSV에 그대로 있음).
    already_scored = set()
    if not df_m1_eval.empty:
        already_scored = {(r["query_id"], r["tag"]) for _, r in df_m1_eval.iterrows()}

    all_pairs = sorted(pairs_set)  # 셔플 전 결정론적 기준 순서
    print(f"\nmethod-1과 겹치는 쌍(재검사 신뢰도용): {len(already_scored & pairs_set)}")
    print(f"전량 블라인드 재채점 대상: {len(all_pairs)}")

    # ========================================================================
    # Step 3: 전 쌍을 셔플 — eval_id가 arm을 누출하지 않도록 반드시 전체를 섞는다
    # ========================================================================
    rng = random.Random(config.SEED)
    rng.shuffle(all_pairs)

    # ========================================================================
    # Step 4: 블라인드 시트 작성 — score/comment는 전 행 공란
    # ========================================================================
    blind_rows = []
    mapping_rows = []

    for i, pair in enumerate(all_pairs, start=1):
        query_id, tag = pair
        details = pair_details[pair]
        eval_id = f"e{i:03d}"

        blind_rows.append({
            "eval_id": eval_id,
            "query_id": query_id,
            "prompt_text": details.get("prompt_text", ""),  # Step 5에서 채움
            "band": details["band"],
            "song": details["song"],
            "url": details["url"],
            "score": "",
            "comment": "",
        })

        mapping_rows.append({
            "eval_id": eval_id,
            "query_id": query_id,
            "tag": tag,
            "arms": "|".join(sorted(set(details["arms"]))),
            "rank_A": details["ranks"]["A"],
            "rank_B": details["ranks"]["B"],
            "rank_C": details["ranks"]["C"],
            "lyr_rank": details["lyr_rank"],
            "acou_rank": details["acou_rank"],
            "acou_match": details["acou_match"],
            "in_method1": pair in already_scored,
        })

    # ========================================================================
    # Step 5: Fill in prompt_text from query targets
    # ========================================================================
    targets_csv = config.OUT_DIR / "query_acoustic_targets.csv"
    if targets_csv.exists():
        df_targets = pd.read_csv(targets_csv)
        prompt_map = dict(zip(df_targets["query_id"], df_targets["prompt_text"]))
        for row in blind_rows:
            if row["query_id"] in prompt_map:
                row["prompt_text"] = prompt_map[row["query_id"]]

    # ========================================================================
    # Step 6: Output
    # ========================================================================
    df_blind = pd.DataFrame(blind_rows)
    blind_csv = config.OUT_DIR / "phase2_blind_sheet.csv"
    df_blind.to_csv(blind_csv, index=False, encoding="utf-8")
    print(f"\nSaved blind sheet to {blind_csv} ({len(df_blind)} rows)")

    df_mapping = pd.DataFrame(mapping_rows)
    mapping_csv = config.OUT_DIR / "phase2_blind_mapping.csv"
    df_mapping.to_csv(mapping_csv, index=False, encoding="utf-8")
    print(f"Saved unmask mapping to {mapping_csv} (DO NOT OPEN until after evaluation)")

    print(
        "\n--- READY FOR BLIND EVALUATION ---"
        f"\nFill in 'score' (0-10 integer) and 'comment' in:"
        f"\n  {blind_csv}"
        "\nAfter completing all scores, run:"
        "\n  python src/method-2/06_unmask_and_report.py (when available)"
    )


if __name__ == "__main__":
    build_blind_sheet()
