"""Stage 1: per-song lyrics profiling (desc + 2 co-equal category keywords) + QC sheet.

Independent of the 00-05 embedding/search pipeline -- no arms, no queries, no search.
See DESIGN.md Section 1b / 6-02b. 2026-07-17: category1/category2 replace the earlier
main/sub ranking (14-song pilot found 29% rank flips -- see notes/03-stage1-handoff.md).

Outputs:
  - out/song_profiles.csv: tag, band, song, desc, category1, category2
  - out/profile_qc_sheet.csv: QC scoring form (human fills in score/comment)
"""
from pathlib import Path
import json
import random
import re
import sys
import time
from datetime import datetime, timezone

import pandas as pd
from groq import Groq, APIError

import config

# Windows consoles default to cp949/cp1252 and crash on Korean/Japanese output otherwise.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
PROGRESS_PATH = config.OUT_DIR / "stage2_full_profiling_progress.json"


def save_progress(progress, **fields):
    progress.update(fields)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

RESPONSE_RE = re.compile(
    r"DESC:\s*(?P<desc>.+?)\s*\n+\s*CATEGORY1:\s*(?P<cat1>.+?)\s*\n+\s*CATEGORY2:\s*(?P<cat2>.+?)\s*$",
    re.DOTALL,
)


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


def parse_profile_response(text):
    """Parse DESC:/CATEGORY1:/CATEGORY2: lines out of the LLM response. Returns None on failure."""
    match = RESPONSE_RE.search(text.strip())
    if not match:
        return None
    desc = match.group("desc").strip()
    cat1 = match.group("cat1").strip()
    cat2 = match.group("cat2").strip()
    if not desc or not cat1 or not cat2:
        return None
    return desc, cat1, cat2


def profile_songs():
    """Generate per-song desc/keyword profiles and build the QC scoring sheet.

    Source-of-truth input is work/transcripts/<tag>.txt (raw ASR lyrics, PROFILE_PROMPT).
    Falls back to the already-committed out/texts_summary.csv (PROFILE_PROMPT_FROM_SUMMARY,
    a lower-fidelity summary-of-a-summary) only when a transcript is missing for a tag.
    """
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_dir = config.WORK_DIR / "transcripts"

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    client = Groq(api_key=api_key)

    df_songs = pd.read_csv(config.SONGS_CSV)
    df_songs = df_songs[df_songs["tag"].isin(config.SAMPLE_TAGS)].reset_index(drop=True)

    if len(df_songs) == 0:
        print(f"ERROR: No songs found in {config.SONGS_CSV} with SAMPLE_TAGS")
        sys.exit(1)

    print(f"Found {len(df_songs)} songs")

    progress = {
        "step": "stage1_profiling_full_catalog",
        "n_total": len(df_songs),
        "n_done": 0,
        "n_failed": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_progress(progress, status="in_progress")

    summaries_csv = config.OUT_DIR / "texts_summary.csv"
    summary_by_tag = {}
    if summaries_csv.exists():
        df_summaries = pd.read_csv(summaries_csv)
        summary_by_tag = dict(zip(df_summaries["tag"], df_summaries["text"]))

    # === Step 1: Build per-song profiles (desc + keyword_main + keyword_sub) ===
    print("\n=== Building song profiles (Stage 1) ===")

    profiles_csv = config.OUT_DIR / "song_profiles.csv"

    existing_profile = set()
    profile_results = []
    if profiles_csv.exists():
        df_existing = pd.read_csv(profiles_csv)
        existing_profile = set(df_existing["tag"])
        profile_results = df_existing.to_dict("records")

    failed_tags = []

    for idx, row in df_songs.iterrows():
        tag = row["tag"]
        band = row["band"]
        song = row["song"]

        if tag in existing_profile:
            print(f"[{idx+1}/{len(df_songs)}] {tag} - already profiled (skip)")
            continue

        transcript_file = transcripts_dir / f"{tag}.txt"
        if transcript_file.exists():
            lyrics = transcript_file.read_text(encoding="utf-8")
            prompt = config.PROFILE_PROMPT.format(lyrics=lyrics)
            source = "transcript"
        elif tag in summary_by_tag:
            prompt = config.PROFILE_PROMPT_FROM_SUMMARY.format(summary=summary_by_tag[tag])
            source = "summary-fallback"
        else:
            print(f"[{idx+1}/{len(df_songs)}] {tag} - no transcript or summary found (skip)")
            continue

        print(f"[{idx+1}/{len(df_songs)}] {tag} - profiling (source={source})...")

        try:
            def call_profile():
                return client.chat.completions.create(
                    model=config.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=config.GROQ_TEMPERATURE,
                )

            response = retry_with_backoff(call_profile)
            raw_text = response.choices[0].message.content
            parsed = parse_profile_response(raw_text)

            if parsed is None:
                print(f"  ERROR: could not parse DESC/MAIN/SUB from response:\n{raw_text}")
                failed_tags.append(tag)
                continue

            desc, category1, category2 = parsed
            profile_results.append({
                "tag": tag,
                "band": band,
                "song": song,
                "desc": desc,
                "category1": category1,
                "category2": category2,
                "source": source,
            })
            # Save after every song so a mid-run crash doesn't lose completed work
            # (idempotent cache above skips these tags on the next run).
            pd.DataFrame(profile_results).to_csv(profiles_csv, index=False, encoding="utf-8")
            print(f"    (ok) CATEGORY1={category1} CATEGORY2={category2}")
        except Exception as e:
            print(f"  ERROR profiling {tag}: {e}")
            save_progress(progress, status="error", n_done=len(profile_results), n_failed=len(failed_tags))
            raise

        if (idx + 1) % 10 == 0 or (idx + 1) == len(df_songs):
            save_progress(
                progress, status="in_progress",
                n_done=len(profile_results), n_failed=len(failed_tags),
            )

    if failed_tags:
        print(f"\nERROR: failed to parse profile for {len(failed_tags)} song(s): {failed_tags}")
        print("Fix the prompt or re-run -- already-succeeded songs are cached and will be skipped.")
        save_progress(progress, status="error", n_done=len(profile_results), n_failed=len(failed_tags))
        sys.exit(1)

    save_progress(progress, status="done", n_done=len(profile_results), n_failed=len(failed_tags))

    df_profiles = pd.DataFrame(profile_results)
    df_profiles.to_csv(profiles_csv, index=False, encoding="utf-8")
    print(f"\nSaved song profiles to {profiles_csv} ({len(df_profiles)} songs)")

    # === Step 2: Build QC scoring sheet (one row per song, no dedup needed) ===
    print("\n=== Building QC sheet ===")

    qc_csv = config.OUT_DIR / "profile_qc_sheet.csv"

    if qc_csv.exists():
        df_qc_existing = pd.read_csv(qc_csv)
        already_scored = set(
            df_qc_existing.loc[df_qc_existing["score"].notna(), "tag"]
        )
        print(f"  {qc_csv} already exists with {len(already_scored)} scored row(s) -- preserving them")
        existing_by_tag = df_qc_existing.set_index("tag").to_dict("index")
    else:
        existing_by_tag = {}

    df_songs_url = df_songs.set_index("tag")["url"].to_dict()

    qc_rows = []
    tags_shuffled = list(df_profiles["tag"])
    random.Random(config.SEED).shuffle(tags_shuffled)

    profile_by_tag = df_profiles.set_index("tag").to_dict("index")

    for pair_id_num, tag in enumerate(tags_shuffled, 1):
        pair_id = f"p{pair_id_num:03d}"
        prof = profile_by_tag[tag]
        prior = existing_by_tag.get(tag, {})

        qc_rows.append({
            "pair_id": pair_id,
            "tag": tag,
            "band": prof["band"],
            "song": prof["song"],
            "url": df_songs_url.get(tag, ""),
            "desc": prof["desc"],
            "category1": prof["category1"],
            "category2": prof["category2"],
            "source": prof.get("source", ""),
            "score": prior.get("score", ""),
            "comment": prior.get("comment", ""),
        })

    df_qc = pd.DataFrame(qc_rows)
    df_qc.to_csv(qc_csv, index=False, encoding="utf-8")
    print(f"Saved QC sheet to {qc_csv} ({len(df_qc)} rows)")

    n_fallback = sum(1 for r in profile_results if r.get("source") == "summary-fallback")
    if n_fallback:
        print(
            f"\nNOTE: {n_fallback} song(s) profiled from texts_summary.csv (transcript "
            "not available on this machine), not raw lyrics -- see 'source' column in "
            "song_profiles.csv. Lower fidelity than PROFILE_PROMPT; re-run against real "
            "transcripts once available."
        )

    # QC checkpoint
    print(
        "\n--- QC CHECKPOINT ---"
        "\nBefore scoring, please verify that desc entries do not contain verbatim"
        "\nlyrics quotes (spot-check 3+ entries in song_profiles.csv)."
        "\n\nScoring rubric: README.md section '프로파일 QC 채점 가이드'"
        "\n(no blind requirement for this stage -- it is not an arm comparison)."
    )


if __name__ == "__main__":
    profile_songs()
