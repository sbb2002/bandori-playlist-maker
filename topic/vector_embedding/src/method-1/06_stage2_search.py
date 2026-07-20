"""Stage 2: difficulty-tiered natural-language search over Stage 1's song desc.

Not an arm comparison (raw/summary/keyword) -- song-side text is song_profiles.csv's
`desc` only. Queries are config.STAGE2_QUERIES (T1 literal / T2 idiomatic / T3
metaphorical, 2 each). For each query: LLM-expand (same template as 02_build_texts.py)
-> embed -> cosine top-K against all 30 song descs -> write a blank 0-10 scoring sheet.

Writes out/stage2_progress.json throughout so progress is visible without tailing logs.

Outputs:
  - out/stage2_queries_expanded.csv: query_id, tier, prompt_text, expanded_text
  - out/stage2_eval_sheet.csv: query_id, tier, prompt_text, rank, tag, band, song, url,
    cosine, score (blank, 0-10), comment (blank)
  - out/stage2_progress.json: {step: status} + timestamps
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

PROGRESS_PATH = config.OUT_DIR / "stage2_progress.json"


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
                print(f"  Retry {attempt + 1}/{max_retries} after {delay}s ({e})")
                time.sleep(delay)
            else:
                raise


def expand_queries(client, progress):
    queries_csv = config.OUT_DIR / "stage2_queries_expanded.csv"
    existing = set()
    results = []
    if queries_csv.exists():
        df_existing = pd.read_csv(queries_csv)
        existing = set(df_existing["query_id"])
        results = df_existing.to_dict("records")

    total = len(config.STAGE2_QUERIES)
    save_progress(progress, "query_expansion", "in_progress", n_done=len(existing), n_total=total)

    for query_id, spec in config.STAGE2_QUERIES.items():
        if query_id in existing:
            print(f"  {query_id} - already expanded (skip)")
            continue

        print(f"  Expanding {query_id} ({spec['tier']})...")
        expand_prompt = (
            f'사용자가 플레이리스트를 요청했다: "{spec["text"]}"\n'
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
            "tier": spec["tier"],
            "prompt_text": spec["text"],
            "expanded_text": expanded_text,
        })
        pd.DataFrame(results).to_csv(queries_csv, index=False, encoding="utf-8")
        print(f"    (ok) {expanded_text[:60]}...")
        save_progress(progress, "query_expansion", "in_progress", n_done=len(results), n_total=total)

    save_progress(progress, "query_expansion", "done", n_done=len(results), n_total=total)
    return pd.DataFrame(results)


def embed_and_search(df_queries, progress):
    save_progress(progress, "song_embedding", "in_progress")

    profiles_csv = config.OUT_DIR / "song_profiles.csv"
    df_songs = pd.read_csv(profiles_csv)
    df_urls = pd.read_csv(config.SONGS_CSV).set_index("tag")["url"].to_dict()

    print(f"\nLoading embedding model: {config.EMBED_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBED_MODEL)

    print(f"Embedding {len(df_songs)} song descs...")
    song_vecs = model.encode(
        df_songs["desc"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )
    save_progress(progress, "song_embedding", "done", n_songs=len(df_songs))

    save_progress(progress, "query_embedding", "in_progress")
    print(f"Embedding {len(df_queries)} expanded queries...")
    query_vecs = model.encode(
        df_queries["expanded_text"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )
    save_progress(progress, "query_embedding", "done", n_queries=len(df_queries))

    save_progress(progress, "search", "in_progress")
    print(f"\nSearching top-{config.STAGE2_TOP_K} per query...")
    rows = []
    for qi, (_, qrow) in enumerate(df_queries.iterrows()):
        sims = song_vecs @ query_vecs[qi]
        top_idx = np.argsort(-sims)[: config.STAGE2_TOP_K]
        for rank, idx in enumerate(top_idx, 1):
            srow = df_songs.iloc[idx]
            rows.append({
                "query_id": qrow["query_id"],
                "tier": qrow["tier"],
                "prompt_text": qrow["prompt_text"],
                "rank": rank,
                "tag": srow["tag"],
                "band": srow["band"],
                "song": srow["song"],
                "url": df_urls.get(srow["tag"], ""),
                "cosine": round(float(sims[idx]), 4),
                "score": "",
                "comment": "",
            })
        print(f"  {qrow['query_id']} ({qrow['tier']}) done")
        save_progress(
            progress, "search", "in_progress",
            n_queries_done=qi + 1, n_queries_total=len(df_queries),
        )

    df_eval = pd.DataFrame(rows)
    eval_csv = config.OUT_DIR / "stage2_eval_sheet.csv"
    df_eval.to_csv(eval_csv, index=False, encoding="utf-8")
    save_progress(progress, "search", "done", n_rows=len(df_eval))
    print(f"\nSaved {len(df_eval)} rows to {eval_csv}")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    client = Groq(api_key=api_key)

    print("=== Step 1: Expand Stage 2 queries ===")
    df_queries = expand_queries(client, progress)

    print("\n=== Step 2: Embed + search ===")
    embed_and_search(df_queries, progress)

    save_progress(progress, "overall", "done")
    print(
        "\n--- READY FOR LISTENING ---"
        f"\nFill in 'score' (0-10) in {config.OUT_DIR / 'stage2_eval_sheet.csv'}"
        "\nafter listening to each recommended song."
    )


if __name__ == "__main__":
    main()
