"""
Step 1: Extract intensity_target and band_filter from queries using LLM.

DESIGN.md §1: LLM extracts two parameters from each query:
  - intensity_target (0.0~1.0, percentile of 661-song catalog)
  - band_filter (one of 11 valid bands, or 'NA')

Output: out/query_targets.csv
  Columns: query_id, intensity_target, band_filter

Uses Groq API (with retry logic and idempotent caching).
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from groq import Groq, APIError

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "01_query_targets_progress.json"


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


def extract_targets(client, progress):
    """
    LLM-extract intensity_target and band_filter from each query.

    Uses DESIGN.md §1 prompt: intensity = sound pressure/density (not emotion),
    band_filter = one of VALID_BANDS or NA.
    """
    targets_csv = config.OUT_DIR / "query_targets.csv"
    existing = {}
    results = []
    if targets_csv.exists():
        df_existing = pd.read_csv(targets_csv)
        existing = {row["query_id"]: row for row in df_existing.to_dict("records")}
        results = df_existing.to_dict("records")

    total = len(config.QUERIES)
    save_progress(progress, "extract_targets", "in_progress", n_done=len(existing), n_total=total)

    for query_id, spec in config.QUERIES.items():
        if query_id in existing:
            print(f"  {query_id} - already extracted (skip)")
            continue

        print(f"  Extracting {query_id}: '{spec['text'][:50]}...'")

        # Format band list for LLM
        band_list_str = ", ".join(config.VALID_BANDS)

        extract_prompt = (
            f"사용자가 플레이리스트를 요청했다: \"{spec['text']}\"\n\n"
            "다음 두 정보를 추출하라:\n\n"
            "1. INTENSITY_TARGET: 이 요청이 원하는 소리의 세기·밀도를 0.0~1.0 사이의 수치로 표현하라.\n"
            "   - INTENSITY = 소리의 텐션(음량·밀도)이지, 감정(밝음/슬픔)이 아니다.\n"
            "   - 0.0 = 전체 카탈로그 중 가장 조용한 곡\n"
            "   - 1.0 = 전체 카탈로그 중 가장 시끄러운 곡\n"
            "   - 해당 없으면 'NA'라고 쓸 것.\n\n"
            "2. BAND_FILTER: 이 요청이 특정 밴드를 명시했다면 그 밴드명을 적어라.\n"
            f"   유효한 밴드: {band_list_str}\n"
            "   (요청에서 밴드 명시가 없으면 'NA'라고 쓸 것.)\n\n"
            "출력 형식(정확히 2줄, 다른 설명 없음):\n"
            "INTENSITY_TARGET: <숫자 또는 NA>\n"
            "BAND_FILTER: <밴드명 또는 NA>"
        )

        def call_extract():
            return client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": extract_prompt}],
                temperature=config.GROQ_TEMPERATURE,
            )

        response = retry_with_backoff(call_extract)
        response_text = response.choices[0].message.content.strip()

        # Parse response
        lines = response_text.split("\n")
        intensity_target = None
        band_filter = None

        for line in lines:
            if "INTENSITY_TARGET:" in line:
                val = line.split("INTENSITY_TARGET:")[-1].strip()
                if val.upper() != "NA":
                    try:
                        intensity_target = float(val)
                        # Clamp to [0, 1]
                        intensity_target = max(0.0, min(1.0, intensity_target))
                    except ValueError:
                        print(f"    WARNING: Could not parse INTENSITY_TARGET: {val}")
                        intensity_target = None
            elif "BAND_FILTER:" in line:
                val = line.split("BAND_FILTER:")[-1].strip().lower()
                if val != "na" and val in config.VALID_BANDS:
                    band_filter = val
                elif val != "na":
                    print(f"    WARNING: Band not in VALID_BANDS: {val}")

        results.append({
            "query_id": query_id,
            "intensity_target": intensity_target,
            "band_filter": band_filter if band_filter else None,
        })
        pd.DataFrame(results).to_csv(targets_csv, index=False, encoding="utf-8")
        print(
            f"    → intensity_target={intensity_target}, "
            f"band_filter={band_filter if band_filter else 'NA'}"
        )
        save_progress(progress, "extract_targets", "in_progress", n_done=len(results), n_total=total)

    save_progress(progress, "extract_targets", "done", n_done=len(results), n_total=total)
    return pd.DataFrame(results)


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    client = Groq(api_key=api_key)

    print("=== Step 1: Extract intensity_target and band_filter ===")
    df_targets = extract_targets(client, progress)

    save_progress(progress, "overall", "done")
    print(
        "\n--- EXTRACTION COMPLETE ---"
        f"\nResults saved to {config.OUT_DIR / 'query_targets.csv'}"
        "\n\nPlease review extracted values:\n"
        f"{df_targets.to_string()}"
    )


if __name__ == "__main__":
    main()
