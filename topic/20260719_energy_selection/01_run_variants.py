"""
Step 1: Run 4 variants × 10 queries × 5 trials through Groq.

DESIGN.md §4: Fetch LLM responses for all combinations, with retry logic and idempotent caching.

Output: out/raw_responses.csv (columns: variant, query_id, trial, parse_success, raw_json,
         start_energy, end_energy, stage_count, stage_energies, resolved_energies)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from groq import Groq, APIError

import config
import prompts
import queries

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "01_run_variants_progress.json"


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"started_at": datetime.now(timezone.utc).isoformat()}


def save_progress(progress):
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def retry_with_backoff(func, max_retries=3, base_delay=2.0):
    """Retry with exponential backoff, following selection_pipeline pattern."""
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


def _extract_json_object(text: str) -> dict:
    """Extract first JSON object from LLM response (code fences allowed).

    Mirrors deployment adapter _extract_json_object() logic.
    """
    text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"JSON object not found: {text[:200]!r}")
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"JSON top-level is not object: {type(obj).__name__}")
    return obj


def _resolve_energies(obj: dict, stage_count: int) -> list:
    """Resolve stage_energies or linear interpolation from start/end.

    If stage_energies is present and valid, use it directly.
    Otherwise, linear interpolate from start_energy to end_energy.
    """
    if isinstance(obj.get("stage_energies"), list):
        energies = obj["stage_energies"]
        if 2 <= len(energies) <= 5:
            return energies

    # Fallback: linear interpolation (DESIGN.md §1, energy.py pattern)
    start = float(obj.get("start_energy", 0.4))
    end = float(obj.get("end_energy", 0.4))
    N = stage_count
    return [start + (end - start) * i / (N - 1) for i in range(N)]


def run_variants(client, progress):
    """
    Run all variant-query-trial combinations through Groq.

    Idempotent: skip already-completed (variant, query_id, trial) tuples.
    """
    output_csv = config.OUT_DIR / "raw_responses.csv"
    existing = {}
    results = []

    if output_csv.exists():
        df_existing = pd.read_csv(output_csv)
        for _, row in df_existing.iterrows():
            key = (row["variant"], row["query_id"], int(row["trial"]))
            existing[key] = row.to_dict()
        results = df_existing.to_dict("records")

    # Total expected: 4 variants × 10 queries × 5 trials = 200
    total = len(config.VARIANTS) * len(queries.QUERIES) * config.N_TRIALS
    done = len(existing)

    print(f"Total: {total}, Already done: {done}")

    for variant in config.VARIANTS:
        prompt_template = prompts.PROMPTS[variant]

        for query_id, query_spec in sorted(queries.QUERIES.items()):
            query_text = query_spec["text"]

            for trial in range(config.N_TRIALS):
                key = (variant, query_id, trial)
                if key in existing:
                    print(f"  {variant} x {query_id} x trial {trial} — skip (cached)")
                    continue

                print(f"  {variant} x {query_id} x trial {trial}...", end=" ", flush=True)

                def call_groq():
                    response = client.chat.completions.create(
                        model=config.GROQ_MODEL,
                        messages=[
                            {"role": "system", "content": prompt_template},
                            {"role": "user", "content": query_text},
                        ],
                        temperature=config.GROQ_TEMPERATURE,
                    )
                    return response.choices[0].message.content.strip()

                try:
                    raw_response = retry_with_backoff(call_groq)
                except Exception as e:
                    print(f"FAILED: {e}")
                    results.append({
                        "variant": variant,
                        "query_id": query_id,
                        "trial": trial,
                        "parse_success": False,
                        "raw_json": None,
                        "start_energy": None,
                        "end_energy": None,
                        "stage_count": None,
                        "stage_energies": None,
                        "resolved_energies": None,
                    })
                    pd.DataFrame(results).to_csv(output_csv, index=False, encoding="utf-8")
                    continue

                # Parse JSON
                parse_success = False
                parsed_obj = None
                try:
                    parsed_obj = _extract_json_object(raw_response)
                    parse_success = True
                except Exception as e:
                    print(f"parse failed: {e}")

                if parse_success:
                    try:
                        start_energy = float(parsed_obj.get("start_energy", 0.4))
                        end_energy = float(parsed_obj.get("end_energy", 0.4))
                        stage_count = int(parsed_obj.get("stage_count", 3))
                        stage_energies = parsed_obj.get("stage_energies")

                        # Resolve array
                        resolved = _resolve_energies(parsed_obj, stage_count)

                        results.append({
                            "variant": variant,
                            "query_id": query_id,
                            "trial": trial,
                            "parse_success": True,
                            "raw_json": json.dumps(parsed_obj, ensure_ascii=False),
                            "start_energy": start_energy,
                            "end_energy": end_energy,
                            "stage_count": stage_count,
                            "stage_energies": json.dumps(stage_energies, ensure_ascii=False) if stage_energies else None,
                            "resolved_energies": json.dumps(resolved, ensure_ascii=False),
                        })
                        print(f"ok")
                    except Exception as e:
                        print(f"extraction failed: {e}")
                        results.append({
                            "variant": variant,
                            "query_id": query_id,
                            "trial": trial,
                            "parse_success": False,
                            "raw_json": json.dumps(parsed_obj, ensure_ascii=False),
                            "start_energy": None,
                            "end_energy": None,
                            "stage_count": None,
                            "stage_energies": None,
                            "resolved_energies": None,
                        })
                else:
                    results.append({
                        "variant": variant,
                        "query_id": query_id,
                        "trial": trial,
                        "parse_success": False,
                        "raw_json": None,
                        "start_energy": None,
                        "end_energy": None,
                        "stage_count": None,
                        "stage_energies": None,
                        "resolved_energies": None,
                    })

                # Save incrementally
                pd.DataFrame(results).to_csv(output_csv, index=False, encoding="utf-8")
                progress["n_done"] = len(results)
                progress["n_total"] = total
                save_progress(progress)

    return pd.DataFrame(results)


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    client = Groq(api_key=api_key)

    print("=== Step 1: Run all variant-query-trial combinations ===")
    df_results = run_variants(client, progress)

    # Summary
    parse_success_count = df_results["parse_success"].sum()
    total_count = len(df_results)
    success_rate = 100.0 * parse_success_count / total_count if total_count > 0 else 0

    print(
        f"\n--- RUN COMPLETE ---\n"
        f"Total trials: {total_count}\n"
        f"Parse success: {parse_success_count} ({success_rate:.1f}%)\n"
        f"Results saved to {config.OUT_DIR / 'raw_responses.csv'}\n"
    )

    progress["status"] = "done"
    save_progress(progress)


if __name__ == "__main__":
    main()
