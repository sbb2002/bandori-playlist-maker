"""Build text variants (summary, keyword) and expand queries using Groq LLM.

Outputs:
  - out/texts_summary.csv: LLM-generated mood summaries
  - out/texts_keyword.csv: LLM-extracted keywords
  - out/queries_expanded.csv: LLM-expanded user prompts
"""
from pathlib import Path
import csv
import sys
import time

import pandas as pd
from groq import Groq, APIError

import config

SCRIPT_DIR = Path(__file__).parent


def retry_with_backoff(func, max_retries=3, base_delay=2.0):
    """Retry a function with exponential backoff."""
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


def build_texts():
    """Build text variants and expand queries."""
    # Setup directories
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_dir = config.WORK_DIR / "transcripts"

    # Load Groq API key
    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Load songs and filter to SAMPLE_TAGS
    df_songs = pd.read_csv(config.SONGS_CSV)
    df_songs = df_songs[df_songs["tag"].isin(config.SAMPLE_TAGS)].reset_index(drop=True)

    if len(df_songs) == 0:
        print(f"ERROR: No songs found in {config.SONGS_CSV} with SAMPLE_TAGS")
        sys.exit(1)

    print(f"Found {len(df_songs)} songs")

    # === Step 1: Build text variants (summary & keyword) ===
    print("\n=== Building text variants (summary & keyword) ===")

    # Load existing results to avoid reprocessing
    summary_csv = config.OUT_DIR / "texts_summary.csv"
    keyword_csv = config.OUT_DIR / "texts_keyword.csv"

    existing_summary = set()
    existing_keyword = set()

    if summary_csv.exists():
        df_summary = pd.read_csv(summary_csv)
        existing_summary = set(df_summary["tag"])
    if keyword_csv.exists():
        df_keyword = pd.read_csv(keyword_csv)
        existing_keyword = set(df_keyword["tag"])

    summary_results = [] if not summary_csv.exists() else pd.read_csv(summary_csv).to_dict("records")
    keyword_results = [] if not keyword_csv.exists() else pd.read_csv(keyword_csv).to_dict("records")

    for idx, row in df_songs.iterrows():
        tag = row["tag"]
        band = row["band"]
        song = row["song"]

        # Load transcript
        transcript_file = transcripts_dir / f"{tag}.txt"
        if not transcript_file.exists():
            print(f"[{idx+1}/{len(df_songs)}] {tag} - transcript not found (skip)")
            continue

        lyrics = transcript_file.read_text(encoding="utf-8")

        print(f"[{idx+1}/{len(df_songs)}] {tag}")

        # Build summary (if not cached)
        if tag not in existing_summary:
            print(f"  Building summary...")
            prompt_summary = (
                "다음은 어느 노래의 가사다(일본어 또는 영어).\n"
                "이 노래의 정서·분위기·에너지를 한국어 3문장으로 서술하라.\n"
                "규칙: 가사 원문의 문장이나 구절을 인용·번역해 옮기지 말 것. 곡 제목이나 고유명사를 쓰지 말 것.\n"
                "감정(예: 쓸쓸함, 벅참), 분위기(예: 몽환적, 공격적), 에너지(예: 잔잔함, 질주감) 위주로만 서술할 것.\n"
                f"\n가사:\n{lyrics}"
            )

            try:
                def call_summary():
                    return client.chat.completions.create(
                        model=config.GROQ_MODEL,
                        messages=[{"role": "user", "content": prompt_summary}],
                        temperature=config.GROQ_TEMPERATURE,
                    )

                response = retry_with_backoff(call_summary)
                summary_text = response.choices[0].message.content.strip()
                summary_results.append({"tag": tag, "band": band, "song": song, "text": summary_text})
                print(f"    (ok) summary generated")
            except Exception as e:
                print(f"  ERROR generating summary: {e}")
                raise

        # Build keyword (if not cached)
        if tag not in existing_keyword:
            print(f"  Building keywords...")
            prompt_keyword = (
                "다음은 어느 노래의 가사다(일본어 또는 영어).\n"
                "이 노래의 감정·분위기를 나타내는 한국어 키워드 8개를 골라라.\n"
                "규칙: 명사 또는 형용사만. 가사 단어를 그대로 옮기지 말 것. 쉼표로 구분해 한 줄로만 출력할 것.\n"
                f"\n가사:\n{lyrics}"
            )

            try:
                def call_keyword():
                    return client.chat.completions.create(
                        model=config.GROQ_MODEL,
                        messages=[{"role": "user", "content": prompt_keyword}],
                        temperature=config.GROQ_TEMPERATURE,
                    )

                response = retry_with_backoff(call_keyword)
                keyword_text = response.choices[0].message.content.strip()
                keyword_results.append({"tag": tag, "band": band, "song": song, "text": keyword_text})
                print(f"    (ok) keywords generated")
            except Exception as e:
                print(f"  ERROR generating keywords: {e}")
                raise

    # Save summary and keyword CSVs
    df_summary = pd.DataFrame(summary_results)
    df_summary.to_csv(summary_csv, index=False, encoding="utf-8")
    print(f"\nSaved summary to {summary_csv}")

    df_keyword = pd.DataFrame(keyword_results)
    df_keyword.to_csv(keyword_csv, index=False, encoding="utf-8")
    print(f"Saved keywords to {keyword_csv}")

    # === Step 2: Expand queries ===
    print("\n=== Expanding queries ===")

    queries_csv = config.OUT_DIR / "queries_expanded.csv"

    # Load existing results
    existing_queries = set()
    query_results = []

    if queries_csv.exists():
        df_queries = pd.read_csv(queries_csv)
        existing_queries = set(df_queries["prompt_id"])
        query_results = df_queries.to_dict("records")

    for prompt_id, prompt_text in config.PROMPTS.items():
        # Extract category and level from prompt_id (e.g., "C1-L1" -> category "C1", level "L1")
        parts = prompt_id.split("-")
        category_id = parts[0]

        # Idempotent: skip if already expanded
        if prompt_id in existing_queries:
            print(f"  {prompt_id} — already expanded (skip)")
            continue

        print(f"  Expanding {prompt_id}...")

        expand_prompt = (
            f'사용자가 플레이리스트를 요청했다: "{prompt_text}"\n'
            "이 요청이 원하는 노래의 정서·분위기·에너지를 한국어 2~3문장으로 더 풍부하게 서술하라.\n"
            "곡 제목·아티스트·장르 명칭은 쓰지 말고, 감정과 분위기 서술만 출력할 것."
        )

        try:
            def call_expand():
                return client.chat.completions.create(
                    model=config.GROQ_MODEL,
                    messages=[{"role": "user", "content": expand_prompt}],
                    temperature=config.GROQ_TEMPERATURE,
                )

            response = retry_with_backoff(call_expand)
            expanded_text = response.choices[0].message.content.strip()
            query_results.append({
                "prompt_id": prompt_id,
                "category_id": category_id,
                "level": parts[1] if len(parts) > 1 else "",
                "prompt_text": prompt_text,
                "expanded_text": expanded_text,
            })
            print(f"    (ok) expanded")
        except Exception as e:
            print(f"  ERROR expanding {prompt_id}: {e}")
            raise

    # Save queries CSV
    df_queries = pd.DataFrame(query_results)
    df_queries.to_csv(queries_csv, index=False, encoding="utf-8")
    print(f"\nSaved expanded queries to {queries_csv}")

    # QC checkpoint
    print(
        "\n--- QC CHECKPOINT ---"
        "\nBefore proceeding to step 03, please verify that summaries/keywords do not"
        "\ncontain verbatim lyrics quotes:"
        "\n  1. Spot-check 3+ entries in texts_summary.csv"
        "\n  2. Spot-check 3+ entries in texts_keyword.csv"
        "\nIf no direct quotes found, proceed to 03_embed.py"
    )


if __name__ == "__main__":
    build_texts()
