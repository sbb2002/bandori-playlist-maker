"""Step 2 (v3): Lyric cosine scores for Stage C (Method 2 only).

DESIGN_v3.md §1: same method as v1 arm2 (topic/selection_pipeline/03_lyric_candidates.py) —
LLM query expansion -> BAAI/bge-m3 embedding -> cosine similarity. Difference from v1: this
saves the FULL {idx: score} vector per query (all 661 songs), not just top-N ranks, because
build_setlist_with_stage_c() re-derives top-N itself after band filtering (DESIGN_v3.md §0).

Output: out/v3/lyric_scores.json  {query_id: {idx(str): cosine_score}}
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import config_v3 as config
from groq import Groq, APIError

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def expand_queries(client):
    expanded_path = config.OUT_DIR / "queries_expanded_v3.json"
    existing = {}
    if expanded_path.exists():
        existing = json.loads(expanded_path.read_text(encoding="utf-8"))

    for query_id, spec in config.QUERIES.items():
        if query_id in existing:
            print(f"  {query_id} - already expanded (skip)")
            continue
        text = spec["text"]
        print(f"  Expanding {query_id}: '{text[:50]}...'")
        # Exact template reused from topic/selection_pipeline/03_lyric_candidates.py (v1 arm2).
        expand_prompt = (
            f'사용자가 플레이리스트를 요청했다: "{text}"\n'
            "이 요청이 원하는 노래의 정서·분위기·에너지를 한국어 2~3문장으로 더 풍부하게 서술하라.\n"
            "곡 제목·아티스트·장르 명칭은 쓰지 말고, 감정과 분위기 서술만 출력할 것."
        )

        def call():
            return client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": expand_prompt}],
                temperature=0.0,
            )

        response = retry_with_backoff(call)
        existing[query_id] = response.choices[0].message.content.strip()
        expanded_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    (ok) {existing[query_id][:60]}...")

    return existing


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.OUT_DIR / "lyric_scores.json"
    if out_path.exists():
        print(f"Output already exists: {out_path}")
        return

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    print("=== Expand queries ===")
    expanded = expand_queries(client)

    print("\n=== Embed + score ===")
    df_desc = pd.read_csv(config.IDX_DESC_CSV)  # idx, desc
    print(f"Loading embedding model: {config.EMBED_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBED_MODEL)

    print(f"Embedding {len(df_desc)} song descs...")
    song_vecs = model.encode(df_desc["desc"].tolist(), normalize_embeddings=True, show_progress_bar=False)

    query_ids = list(config.QUERIES.keys())
    query_texts = [expanded[qid] for qid in query_ids]
    print(f"Embedding {len(query_texts)} expanded queries...")
    query_vecs = model.encode(query_texts, normalize_embeddings=True, show_progress_bar=False)

    scores = {}
    for i, qid in enumerate(query_ids):
        sims = song_vecs @ query_vecs[i]
        scores[qid] = {str(idx): round(float(s), 5) for idx, s in zip(df_desc["idx"], sims)}
        print(f"  {qid}: top idx = {df_desc['idx'].iloc[int(np.argmax(sims))]}")

    out_path.write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
