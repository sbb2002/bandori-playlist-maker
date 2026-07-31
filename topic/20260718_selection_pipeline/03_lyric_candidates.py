"""
Step 3: Lyric candidate screening (arm 2·3 shared).

DESIGN.md §3: Use 06_stage2_search.py's method exactly (no redesign):
  1. LLM-expand query to 2~3 sentences
  2. Embed query + song descs with BAAI/bge-m3 (normalized)
  3. Cosine similarity top-N (where N = max(15, ceil(0.20 * eligible_pool_size)))
  4. Save rank_in_pool for later join

Output: out/query_lyric_candidates.csv
  Columns: query_id, tag, band, lyric_cosine, rank_in_pool
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from groq import Groq, APIError

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "03_lyric_candidates_progress.json"


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"steps": {}, "started_at": datetime.now(timezone.utc).isoformat()}


def save_progress(progress, step, status, **extra):
    progress["steps"][step] = {"status": status, **extra}
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def retry_with_backoff(func, max_retries=3, base_delay=2.0):
    for attempt in range(max_retries):
        try:
            return func()
        except (APIError, Exception) as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"    Retry {attempt + 1}/{max_retries} after {delay}s ({e})")
                time.sleep(delay)
            else:
                raise


def expand_queries(client, progress):
    """
    Expand queries using LLM (same template as 06_stage2_search.py).
    Cache the results.
    """
    targets_csv = config.OUT_DIR / "query_targets.csv"
    df_targets = pd.read_csv(targets_csv)

    queries_expanded_csv = config.OUT_DIR / "queries_expanded.csv"
    existing = set()
    results = []
    if queries_expanded_csv.exists():
        df_existing = pd.read_csv(queries_expanded_csv)
        existing = set(df_existing["query_id"])
        results = df_existing.to_dict("records")

    total = len(df_targets)
    save_progress(progress, "query_expansion", "in_progress", n_done=len(existing), n_total=total)

    for _, row in df_targets.iterrows():
        query_id = row["query_id"]
        if query_id in existing:
            print(f"  {query_id} - already expanded (skip)")
            continue

        spec = config.QUERIES[query_id]
        prompt_text = spec["text"]

        print(f"  Expanding {query_id}: '{prompt_text[:50]}...'")

        # Exact template from 06_stage2_search.py lines 79-82
        expand_prompt = (
            f'사용자가 플레이리스트를 요청했다: "{prompt_text}"\n'
            "이 요청이 원하는 노래의 정서·분위기·에너지를 한국어 2~3문장으로 더 풍부하게 서술하라.\n"
            "곡 제목·아티스트·장르 명칭은 쓰지 말고, 감정과 분위기 서술만 출력할 것."
        )

        def call_expand():
            return client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": expand_prompt}],
                temperature=config.GROQ_TEMPERATURE,
            )

        response = retry_with_backoff(call_expand)
        expanded_text = response.choices[0].message.content.strip()
        results.append({
            "query_id": query_id,
            "prompt_text": prompt_text,
            "expanded_text": expanded_text,
        })
        pd.DataFrame(results).to_csv(queries_expanded_csv, index=False, encoding="utf-8")
        print(f"    (ok) {expanded_text[:60]}...")
        save_progress(progress, "query_expansion", "in_progress", n_done=len(results), n_total=total)

    save_progress(progress, "query_expansion", "done", n_done=len(results), n_total=total)
    return pd.DataFrame(results)


def embed_and_search(df_queries_expanded, df_targets, progress):
    """
    Embed queries + song profiles, compute cosine similarity, extract top-N per query.
    """
    save_progress(progress, "song_embedding", "in_progress")

    # Load song profiles
    # NOTE: song_profiles.csv already carries "tag", "band", "song" columns
    # that are identical to full_catalog_songs.csv's (verified: 661/661 rows,
    # zero mismatches). A previous version merged in full_catalog_songs.csv's
    # "band"/"song" columns here, but since both frames already have
    # non-key columns named "band"/"song", pandas.merge silently renamed them
    # to "band_x"/"band_y"/"song_x"/"song_y" — the "band"/"song" columns used
    # below (eligible_mask, srow["band"], srow["song"]) would then raise a
    # KeyError. Dropped the redundant merge; song_profiles.csv's own columns
    # are used directly.
    print(f"\nLoading song profiles...")
    df_songs = pd.read_csv(config.SONG_PROFILES_CSV)
    print(f"  Loaded {len(df_songs)} song profiles")

    # Load embedding model
    print(f"Loading embedding model: {config.EMBED_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBED_MODEL)

    # Embed all song descs
    print(f"Embedding {len(df_songs)} song descs...")
    song_vecs = model.encode(
        df_songs["desc"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )
    save_progress(progress, "song_embedding", "done", n_songs=len(df_songs))

    # Embed queries
    save_progress(progress, "query_embedding", "in_progress")
    print(f"Embedding {len(df_queries_expanded)} expanded queries...")
    query_vecs = model.encode(
        df_queries_expanded["expanded_text"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )
    save_progress(progress, "query_embedding", "done", n_queries=len(df_queries_expanded))

    # Search
    save_progress(progress, "search", "in_progress")
    print(f"\nSearching candidates...")
    candidates_csv = config.OUT_DIR / "query_lyric_candidates.csv"
    existing = set()
    results = []
    if candidates_csv.exists():
        df_existing = pd.read_csv(candidates_csv)
        existing = set(df_existing["query_id"])
        results = df_existing.to_dict("records")

    for qi, (_, qrow) in enumerate(df_queries_expanded.iterrows()):
        query_id = qrow["query_id"]
        if query_id in existing:
            print(f"  {query_id} - already searched (skip)")
            continue

        # Get band_filter from targets
        target_row = df_targets[df_targets["query_id"] == query_id].iloc[0]
        band_filter = target_row["band_filter"]

        # Define eligible_pool (band_filter applied BEFORE candidate screening)
        if pd.notna(band_filter) and band_filter:
            eligible_mask = df_songs["band"] == band_filter
        else:
            eligible_mask = pd.Series([True] * len(df_songs))

        eligible_indices = np.where(eligible_mask)[0]
        eligible_pool_size = len(eligible_indices)

        # Compute candidate pool size N
        N = config.compute_candidate_pool_size(eligible_pool_size)

        print(f"  {query_id} (band={band_filter if band_filter else 'NA'}, "
              f"eligible={eligible_pool_size}, N={N})")

        # Compute similarities for eligible songs only
        sims_all = song_vecs @ query_vecs[qi]
        sims_eligible = sims_all[eligible_indices]

        # Get top-N in eligible pool
        top_idx_in_eligible = np.argsort(-sims_eligible)[:N]
        top_idx_global = eligible_indices[top_idx_in_eligible]

        for rank, idx in enumerate(top_idx_in_eligible, 1):
            global_idx = top_idx_global[rank - 1]
            srow = df_songs.iloc[global_idx]
            results.append({
                "query_id": query_id,
                "tag": srow["tag"],
                "band": srow["band"],
                "lyric_cosine": round(float(sims_all[global_idx]), 4),
                "rank_in_pool": rank,
            })

        pd.DataFrame(results).to_csv(candidates_csv, index=False, encoding="utf-8")
        save_progress(
            progress, "search", "in_progress",
            n_queries_done=len(set(pd.DataFrame(results)["query_id"])),
            n_queries_total=len(df_queries_expanded),
        )

    save_progress(progress, "search", "done", n_rows=len(results))
    print(f"\nSaved {len(results)} rows to {candidates_csv}")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    client = Groq(api_key=api_key)

    # Load targets (must run 01_query_targets.py first)
    targets_csv = config.OUT_DIR / "query_targets.csv"
    if not targets_csv.exists():
        print(f"ERROR: {targets_csv} not found. Run 01_query_targets.py first.")
        sys.exit(1)
    df_targets = pd.read_csv(targets_csv)

    print("=== Step 3a: Expand queries ===")
    df_queries_expanded = expand_queries(client, progress)

    print("\n=== Step 3b: Embed + search ===")
    embed_and_search(df_queries_expanded, df_targets, progress)

    save_progress(progress, "overall", "done")
    print("\n--- LYRIC CANDIDATE SCREENING COMPLETE ---")


if __name__ == "__main__":
    main()
