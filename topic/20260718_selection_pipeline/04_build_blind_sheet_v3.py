"""Step 4 (v3): Build blind evaluation sheet from method_results.csv.

DESIGN_v3.md §6: union of (query_id, idx) pairs across method1/method2, dedup, shuffle,
strip identity-revealing columns (method, category all excluded from the blind sheet).
"""
import sys
from random import Random

import pandas as pd
import config_v3 as config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(config.OUT_DIR / "method_results.csv")
    print(f"Loaded {len(df)} results from 2 methods")

    query_texts = {qid: spec["text"] for qid, spec in config.QUERIES.items()}

    pairs = set()
    for _, row in df.iterrows():
        pairs.add((row["query_id"], row["idx"]))

    print(f"\nExpected maximum (no overlap): 2 methods x 24 queries x {config.K} ranks = {2*24*config.K} pairs")
    print(f"Actual unique pairs: {len(pairs)}")

    rows_blind = []
    rows_mapping = []
    eval_id = 1
    for query_id, idx in sorted(pairs):
        matches = df[(df["query_id"] == query_id) & (df["idx"] == idx)]
        methods_str = "|".join(sorted(matches["method"].unique()))
        first = matches.iloc[0]

        rows_blind.append({
            "eval_id": eval_id, "query_id": query_id, "prompt_text": query_texts[query_id],
            "band": first["band"], "song": first["song"], "url": first["url"],
            "score": "", "comment": "",
        })
        rows_mapping.append({
            "eval_id": eval_id, "query_id": query_id, "idx": idx,
            "methods": methods_str, "energy": first["energy"],
        })
        eval_id += 1

    rng = Random(config.SHUFFLE_SEED)
    indices = list(range(len(rows_blind)))
    rng.shuffle(indices)
    rows_blind = [rows_blind[i] for i in indices]
    rows_mapping = [rows_mapping[i] for i in indices]
    for i, (rb, rm) in enumerate(zip(rows_blind, rows_mapping), 1):
        rb["eval_id"] = i
        rm["eval_id"] = i

    blind_csv = config.OUT_DIR / "method_blind_sheet_v3.csv"
    mapping_csv = config.OUT_DIR / "method_blind_mapping_v3.csv"
    pd.DataFrame(rows_blind).to_csv(blind_csv, index=False, encoding="utf-8")
    pd.DataFrame(rows_mapping).to_csv(mapping_csv, index=False, encoding="utf-8")

    print(f"\n--- BLIND SHEET COMPLETE (v3) ---")
    print(f"Blind evaluation sheet: {blind_csv}")
    print(f"  {len(rows_blind)} unique (query_id, idx) pairs")
    print(f"Unblinding mapping (DO NOT OPEN BEFORE EVALUATION): {mapping_csv}")


if __name__ == "__main__":
    main()
