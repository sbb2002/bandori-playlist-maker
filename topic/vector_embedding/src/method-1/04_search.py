"""Search and generate evaluation sheet.

Outputs:
  - out/results_top5.csv: raw search results (arm, query, top-5)
  - out/eval_sheet.csv: evaluation form (blind, no arm/level/score info visible)
  - out/eval_mapping.csv: mapping back to arm/level/rank for analysis
"""
from pathlib import Path
import sys
import random
from collections import defaultdict

import numpy as np
import pandas as pd

import config

SCRIPT_DIR = Path(__file__).parent


def search_and_evaluate():
    """Perform cosine search and generate evaluation sheets."""
    # Setup directories
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load embeddings
    embeddings_file = config.OUT_DIR / "embeddings.npz"
    if not embeddings_file.exists():
        print(f"ERROR: {embeddings_file} not found. Run 03_embed.py first.")
        sys.exit(1)

    data = np.load(embeddings_file, allow_pickle=True)
    raw_emb = data["raw"]
    summary_emb = data["summary"]
    keyword_emb = data["keyword"]
    tags = data["tags"].tolist()
    queries = data["queries"]
    query_ids = data["query_ids"].tolist()

    print(f"Loaded embeddings: songs={raw_emb.shape}, queries={queries.shape}")

    # Load songs for URL mapping
    df_songs = pd.read_csv(config.SONGS_CSV)
    df_songs = df_songs[df_songs["tag"].isin(config.SAMPLE_TAGS)]
    url_map = dict(zip(df_songs["tag"], df_songs["url"]))

    # Load queries metadata
    df_queries = pd.read_csv(config.OUT_DIR / "queries_expanded.csv")
    category_map = dict(zip(df_queries["prompt_id"], df_queries["category_id"]))

    # === Perform cosine search for each arm × query ===
    print("\n=== Searching (top-5 per arm per query) ===")

    results_top5 = []
    arms = ["raw", "summary", "keyword"]
    embeddings_map = {"raw": raw_emb, "summary": summary_emb, "keyword": keyword_emb}

    for arm in arms:
        emb = embeddings_map[arm]
        print(f"  {arm}:")
        for q_idx, query_id in enumerate(query_ids):
            query_vec = queries[q_idx]
            # Cosine similarity = dot product (since both are L2-normalized)
            scores = np.dot(emb, query_vec)
            top5_indices = np.argsort(-scores)[:config.TOP_K]

            for rank, song_idx in enumerate(top5_indices, 1):
                tag = tags[song_idx]
                row_data = df_songs[df_songs["tag"] == tag].iloc[0]
                results_top5.append({
                    "arm": arm,
                    "prompt_id": query_id,
                    "rank": rank,
                    "tag": tag,
                    "band": row_data["band"],
                    "song": row_data["song"],
                    "cosine": float(scores[song_idx]),
                })

            print(f"    {query_id}: top-5 (ok)")

    df_results = pd.DataFrame(results_top5)
    results_csv = config.OUT_DIR / "results_top5.csv"
    df_results.to_csv(results_csv, index=False, encoding="utf-8")
    print(f"\nSaved results_top5 to {results_csv}")
    print(f"Results: {len(results_top5)} rows (3 arms × {len(query_ids)} queries × 5 ranks)")

    # === Build evaluation pairs (category_id, tag) dedup ===
    print("\n=== Building evaluation pairs ===")

    # Group top-5 results by (category_id, tag)
    pair_dict = defaultdict(list)  # (category_id, tag) -> list of (arm, prompt_id, rank)

    for _, row in df_results.iterrows():
        prompt_id = row["prompt_id"]
        category_id = category_map[prompt_id]
        tag = row["tag"]
        arm = row["arm"]
        rank = row["rank"]

        pair_key = (category_id, tag)
        pair_dict[pair_key].append({
            "arm": arm,
            "prompt_id": prompt_id,
            "rank": rank,
            "tag": tag,
        })

    # Build eval sheet (unique pairs)
    eval_pairs = []
    mapping_records = []

    # Shuffle before assigning pair_ids so the id sequence leaks no retrieval order
    pair_items = list(pair_dict.items())
    random.Random(config.SEED).shuffle(pair_items)

    for pair_id_num, ((category_id, tag), arm_records) in enumerate(pair_items, 1):
        pair_id = f"p{pair_id_num:03d}"

        # Get category name and L4 description
        category_name = config.CATEGORIES.get(category_id, "")
        l4_prompt_id = f"{category_id}-L4"
        category_desc = config.PROMPTS.get(l4_prompt_id, "")

        # Get song info
        row_data = df_songs[df_songs["tag"] == tag].iloc[0]
        band = row_data["band"]
        song = row_data["song"]
        url = url_map.get(tag, "")

        # Add to eval sheet (blind: no arm/level info visible)
        eval_pairs.append({
            "pair_id": pair_id,
            "category_id": category_id,
            "category_name": category_name,
            "category_desc": category_desc,
            "band": band,
            "song": song,
            "url": url,
            "score": "",  # To be filled by human
            "comment": "",  # To be filled by human
        })

        # Add to mapping (for analysis after eval)
        for arm_record in arm_records:
            mapping_records.append({
                "pair_id": pair_id,
                "arm": arm_record["arm"],
                "prompt_id": arm_record["prompt_id"],
                "rank": arm_record["rank"],
                "tag": arm_record["tag"],
            })

    df_eval = pd.DataFrame(eval_pairs)
    eval_csv = config.OUT_DIR / "eval_sheet.csv"
    df_eval.to_csv(eval_csv, index=False, encoding="utf-8")
    print(f"Saved eval_sheet to {eval_csv}")
    print(f"  {len(eval_pairs)} unique (category, song) pairs")

    df_mapping = pd.DataFrame(mapping_records)
    mapping_csv = config.OUT_DIR / "eval_mapping.csv"
    df_mapping.to_csv(mapping_csv, index=False, encoding="utf-8")
    print(f"Saved eval_mapping to {mapping_csv}")

    # Guidance
    print(
        "\n--- EVALUATION INSTRUCTIONS ---"
        "\nBefore opening results_top5.csv:"
        "\n  1. Open eval_sheet.csv"
        "\n  2. For each row, listen to the song and rate (1-5) how well it matches"
        "\n     the category description (category_desc column)"
        "\n  3. Fill in the 'score' and 'comment' columns"
        "\n  4. Do NOT open results_top5.csv until scoring is complete"
        "\n\nAfter scoring, run 05_analyze.py to compute final metrics"
    )


if __name__ == "__main__":
    search_and_evaluate()
