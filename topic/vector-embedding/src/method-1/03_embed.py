"""Embed text using BGE-M3 model.

Outputs:
  - out/embeddings.npz: song embeddings (raw, summary, keyword) + query embeddings
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

import config

SCRIPT_DIR = Path(__file__).parent


def embed_all():
    """Embed songs and queries using BGE-M3."""
    # Setup directories
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_dir = config.WORK_DIR / "transcripts"

    # Load Sentence Transformer model
    print(f"Loading embedding model: {config.EMBED_MODEL}")
    model = SentenceTransformer(config.EMBED_MODEL)

    # Load songs and filter to SAMPLE_TAGS (maintain order)
    df_songs = pd.read_csv(config.SONGS_CSV)
    df_songs = df_songs[df_songs["tag"].isin(config.SAMPLE_TAGS)]
    # Reorder to match SAMPLE_TAGS order
    df_songs["tag_order"] = df_songs["tag"].apply(lambda t: config.SAMPLE_TAGS.index(t))
    df_songs = df_songs.sort_values("tag_order").reset_index(drop=True)
    df_songs = df_songs.drop("tag_order", axis=1)

    if len(df_songs) == 0:
        print(f"ERROR: No songs found in {config.SONGS_CSV} with SAMPLE_TAGS")
        sys.exit(1)

    print(f"Found {len(df_songs)} songs")

    # === Embed songs (3 arms) ===
    print("\n=== Embedding songs ===")

    # Load text CSVs
    summary_csv = config.OUT_DIR / "texts_summary.csv"
    keyword_csv = config.OUT_DIR / "texts_keyword.csv"

    if not summary_csv.exists():
        print(f"ERROR: {summary_csv} not found. Run 02_build_texts.py first.")
        sys.exit(1)
    if not keyword_csv.exists():
        print(f"ERROR: {keyword_csv} not found. Run 02_build_texts.py first.")
        sys.exit(1)

    df_summary = pd.read_csv(summary_csv)
    df_keyword = pd.read_csv(keyword_csv)

    # Map tag -> text for quick lookup
    summary_map = dict(zip(df_summary["tag"], df_summary["text"]))
    keyword_map = dict(zip(df_keyword["tag"], df_keyword["text"]))

    # Collect texts for each arm
    raw_texts = []
    summary_texts = []
    keyword_texts = []

    for idx, row in df_songs.iterrows():
        tag = row["tag"]

        # Raw: read from transcript
        transcript_file = transcripts_dir / f"{tag}.txt"
        if not transcript_file.exists():
            print(f"ERROR: {transcript_file} not found")
            sys.exit(1)
        raw_text = transcript_file.read_text(encoding="utf-8")
        raw_texts.append(raw_text)

        # Summary and keyword from CSV
        summary_text = summary_map.get(tag, "")
        keyword_text = keyword_map.get(tag, "")
        if not summary_text:
            print(f"ERROR: No summary for {tag}")
            sys.exit(1)
        if not keyword_text:
            print(f"ERROR: No keyword for {tag}")
            sys.exit(1)

        summary_texts.append(summary_text)
        keyword_texts.append(keyword_text)

    # Encode all texts (batch)
    print(f"Encoding {len(df_songs)} songs (raw arm)...")
    raw_embeddings = model.encode(raw_texts, normalize_embeddings=True)

    print(f"Encoding {len(df_songs)} songs (summary arm)...")
    summary_embeddings = model.encode(summary_texts, normalize_embeddings=True)

    print(f"Encoding {len(df_songs)} songs (keyword arm)...")
    keyword_embeddings = model.encode(keyword_texts, normalize_embeddings=True)

    print(f"Embedding shape: {raw_embeddings.shape}")

    # === Embed queries ===
    print("\n=== Embedding queries ===")

    queries_csv = config.OUT_DIR / "queries_expanded.csv"
    if not queries_csv.exists():
        print(f"ERROR: {queries_csv} not found. Run 02_build_texts.py first.")
        sys.exit(1)

    df_queries = pd.read_csv(queries_csv)
    query_ids = df_queries["prompt_id"].tolist()
    query_texts = df_queries["expanded_text"].tolist()

    print(f"Encoding {len(query_texts)} queries...")
    query_embeddings = model.encode(query_texts, normalize_embeddings=True)

    print(f"Query embeddings shape: {query_embeddings.shape}")

    # === Save to NPZ ===
    print("\n=== Saving embeddings ===")

    embeddings_npz = config.OUT_DIR / "embeddings.npz"
    np.savez(
        embeddings_npz,
        raw=raw_embeddings,
        summary=summary_embeddings,
        keyword=keyword_embeddings,
        tags=np.array(config.SAMPLE_TAGS, dtype=object),
        queries=query_embeddings,
        query_ids=np.array(query_ids, dtype=object),
    )

    print(f"Saved embeddings to {embeddings_npz}")


if __name__ == "__main__":
    embed_all()
