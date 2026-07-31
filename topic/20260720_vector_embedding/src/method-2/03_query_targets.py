"""Stage 2: Convert queries to acoustic targets via LLM — DESIGN.md §3.

Takes config.STAGE2_QUERIES and translates each to acoustic axis targets
(INTENSITY, BRIGHTNESS, TEMPO) using LLM. Outputs percentile targets 0.0~1.0 or NA.

Idempotent: queries already in out/query_acoustic_targets.csv are cached.

Output:
  - out/query_acoustic_targets.csv: query_id, tier, prompt_text, intensity_t,
    brightness_t, tempo_t (NA values are empty strings)
  - out/query_targets_progress.json: progress tracking
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from groq import Groq, APIError

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "query_targets_progress.json"


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"started_at": datetime.now(timezone.utc).isoformat()}


def save_progress(progress, **fields):
    progress.update(fields)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def retry_with_backoff(func, max_retries=3, base_delay=2.0):
    """Retry function with exponential backoff."""
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


def parse_targets(text):
    """Parse INTENSITY/BRIGHTNESS/TEMPO lines from LLM response.

    Expected format:
      INTENSITY: <0.0-1.0 or NA>
      BRIGHTNESS: <0.0-1.0 or NA>
      TEMPO: <0.0-1.0 or NA>

    Returns: (intensity_t, brightness_t, tempo_t) or None on parse failure.
    """
    lines = text.strip().split("\n")
    targets = {"INTENSITY": None, "BRIGHTNESS": None, "TEMPO": None}

    for line in lines:
        for key in targets.keys():
            if line.startswith(key + ":"):
                value_str = line[len(key) + 1 :].strip()
                if value_str.upper() == "NA" or value_str == "":
                    targets[key] = "NA"
                else:
                    try:
                        val = float(value_str)
                        if 0.0 <= val <= 1.0:
                            targets[key] = round(val, 3)
                        else:
                            print(f"    WARNING: {key} value {val} out of range [0, 1]")
                            targets[key] = "NA"
                    except ValueError:
                        print(f"    WARNING: could not parse {key}: {value_str}")
                        targets[key] = "NA"

    if all(v is not None for v in targets.values()):
        return (targets["INTENSITY"], targets["BRIGHTNESS"], targets["TEMPO"])
    return None


def query_acoustic_targets():
    """Generate acoustic targets for all stage 2 queries."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Load or create cache
    targets_csv = config.OUT_DIR / "query_acoustic_targets.csv"
    existing = set()
    results = []
    if targets_csv.exists():
        df_existing = pd.read_csv(targets_csv)
        existing = set(df_existing["query_id"])
        results = df_existing.to_dict("records")

    progress = load_progress()
    progress["step"] = "query_acoustic_targets"
    progress["n_total"] = len(config.STAGE2_QUERIES)
    progress["n_done"] = len(existing)
    save_progress(progress, status="in_progress")

    print(f"Generating acoustic targets for {len(config.STAGE2_QUERIES)} queries...")
    print(f"(Using cache: {len(existing)} already done)")

    # Build prompt template
    prompt_template = """다음은 사용자의 노래 요청이다:

"{query}"

이 요청에서 원하는 곡의 음향 특성을 다음 3가지 축으로 정의하라.
각 축은 661곡 카탈로그 내 백분위 목표 (0.0=카탈로그에서 가장 낮음, 1.0=가장 높음).

INTENSITY = 소리의 세기·밀도. 감정이 아니라 순수 음량/밀도 (조용함 ↔ 시끄러움).
  예: "자장가" → 낮음, "헤비메탈" → 높음.
BRIGHTNESS = 장조/단조 축. "밝은 감정"이 아니라 화성적 장단조.
  주의: 단조로도 신나는 곡이 많다. "행복한 노래"라고 해서 항상 높은 값일 필요는 없다.
TEMPO = 곡의 빠르기 (BPM 백분위).

각 축이 요청과 무관하면 "NA"라고 쓸 것. 무관한 축에 억지로 숫자를 채우지 말 것.

출력 형식 (반드시 이 3줄만):
INTENSITY: <0.0~1.0 또는 NA>
BRIGHTNESS: <0.0~1.0 또는 NA>
TEMPO: <0.0~1.0 또는 NA>"""

    for query_id, spec in config.STAGE2_QUERIES.items():
        if query_id in existing:
            print(f"  {query_id} - already done (cache)")
            continue

        print(f"\n  Querying {query_id} ({spec['tier']})...")
        prompt = prompt_template.format(query=spec["text"])

        def call_llm():
            return client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=config.GROQ_TEMPERATURE,
            )

        try:
            response = retry_with_backoff(call_llm)
            raw_text = response.choices[0].message.content.strip()
            print(f"    Response: {raw_text[:80]}...")

            parsed = parse_targets(raw_text)
            if parsed is None:
                print(f"    WARNING: Could not parse response, retrying once...")
                try:
                    response = retry_with_backoff(call_llm)
                    raw_text = response.choices[0].message.content.strip()
                    parsed = parse_targets(raw_text)
                except Exception as e2:
                    print(f"    ERROR: Failed after retry: {e2}")
                    sys.exit(1)

            intensity_t, brightness_t, tempo_t = parsed

            results.append({
                "query_id": query_id,
                "tier": spec["tier"],
                "prompt_text": spec["text"],
                "intensity_t": "" if intensity_t == "NA" else intensity_t,
                "brightness_t": "" if brightness_t == "NA" else brightness_t,
                "tempo_t": "" if tempo_t == "NA" else tempo_t,
            })

            pd.DataFrame(results).to_csv(targets_csv, index=False, encoding="utf-8")
            print(f"    (saved) INTENSITY={intensity_t}, BRIGHTNESS={brightness_t}, TEMPO={tempo_t}")

        except Exception as e:
            print(f"  ERROR on {query_id}: {e}")
            save_progress(progress, status="error", n_done=len(results))
            raise

        progress["n_done"] = len(results)
        save_progress(progress, status="in_progress")

    save_progress(progress, status="done", n_done=len(results))
    print(f"\nSaved acoustic targets for {len(results)} queries to {targets_csv}")


if __name__ == "__main__":
    query_acoustic_targets()
