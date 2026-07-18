"""Step 1 (v3): Extract MoodParameters + band_filter using the REAL production prompt.

DESIGN_v3.md §3: reuses prod_snapshot/adapters/prompt.py's SYSTEM_PROMPT/build_messages/
parse_mood (verbatim production LLM extraction schema) and prod_snapshot/api/band_aliases.py's
detect_bands() (deterministic, no LLM).

Output: out/v3/query_params.json
  [{query_id, text, band_filter: [..], params: {brightness, start_energy, end_energy,
    stage_count, stage_energies, target_minutes, tags, song_type}}]
"""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import config_v3 as config
from groq import Groq, APIError

sys.path.insert(0, str(Path(__file__).parent))
from prod_snapshot.adapters import prompt as prompt_mod
from prod_snapshot.api import band_aliases

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.OUT_DIR / "query_params.json"

    existing = {}
    if out_path.exists():
        for row in json.loads(out_path.read_text(encoding="utf-8")):
            existing[row["query_id"]] = row

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    results = list(existing.values())
    for query_id, spec in config.QUERIES.items():
        if query_id in existing:
            print(f"  {query_id} - already extracted (skip)")
            continue
        text = spec["text"]
        print(f"  Extracting {query_id}: '{text[:50]}...'")

        def call():
            return client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=prompt_mod.build_messages(text),
                temperature=config.GROQ_TEMPERATURE,
            )

        response = retry_with_backoff(call)
        content = response.choices[0].message.content
        params = prompt_mod.parse_mood(content)
        band_filter = sorted(band_aliases.detect_bands(text))

        row = {
            "query_id": query_id,
            "text": text,
            "category": spec["category"],
            "band_filter": band_filter,
            "params": asdict(params),
        }
        results.append(row)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    -> brightness={params.brightness:.2f} start={params.start_energy:.2f} "
              f"end={params.end_energy:.2f} stage_energies={params.stage_energies} "
              f"band_filter={band_filter or 'NA'}")

    print(f"\nSaved {len(results)} rows to {out_path}")


if __name__ == "__main__":
    main()
