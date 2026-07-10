#!/usr/bin/env python3
"""token_gate.py -- Claude Code local transcript token-usage gate.

Aggregates token usage from local Claude Code transcripts
(``~/.claude/projects/**/*.jsonl``) and prints a JSON verdict used by the
"부장" (main session) as a pre-spawn gate, per docs/orgarnization.md §4 / R5.

Standard library only -- no external dependencies, no venv required:

    python src/scripts/token_gate.py
    python src/scripts/token_gate.py --config src/scripts/token_gate_config.json

Output contract (stdout, JSON)::

    {
      "session_pct": 42.0,
      "weekly_pct": 61.5,
      "fable_weekly_pct": 55.0,
      "verdict": "GO",          // GO | HOLD | UNKNOWN
      "checked_at": "2026-07-10T09:00:00+09:00"
    }

Verdict rule: HOLD if session_pct >= 80 or weekly_pct >= 90 or
fable_weekly_pct >= 70, otherwise GO.

Transcript record shape (observed empirically -- see report for the
lines inspected to derive this):

- Each JSONL line is one record. Records relevant to token accounting have
  ``"type": "assistant"`` and a ``"message"`` object with ``"model"`` and
  ``"usage"`` (``input_tokens``, ``output_tokens``,
  ``cache_creation_input_tokens``, ``cache_read_input_tokens``, ...).
- A single assistant turn (one API response, one ``message.id`` /
  ``requestId``) is frequently split across *multiple* JSONL lines (one per
  content block: thinking / text / tool_use). Every such line repeats the
  *same* usage object. Naively summing usage per line double- or
  triple-counts tokens, so aggregation here dedupes by ``message.id``.
- Top-level ``"timestamp"`` is an ISO-8601 UTC string (``...Z``), present on
  assistant records, used for the 7-day weekly window.
- Some records use ``"model": "<synthetic>"`` (e.g. system-generated
  messages); these always carry all-zero usage in observed data, so they are
  harmless to include and are not special-cased.
- Sub-agent transcripts live under
  ``<project>/<session-id>/subagents/agent-*.jsonl`` and are picked up by the
  recursive ``**/*.jsonl`` glob like any other transcript file, since they
  represent real token consumption too.

Known approximation sources (see also token_gate_config.json "_notes"):

1. The denominators (session_limit / weekly_limit / fable_weekly_limit) are
   rough estimates, not values published by Anthropic -- actual plan limits
   are enforced server-side and may use model-weighted "token-equivalent"
   accounting rather than a raw token sum.
2. "Total tokens" per record here = input + output + cache_creation +
   cache_read. Whether the real quota counts cache_read tokens at full
   weight, a discount, or not at all is unconfirmed.
3. "Session" = single most-recently-modified transcript file (by mtime),
   which is a proxy for "the active conversation" but is not guaranteed to
   equal Anthropic's server-side 5-hour session window (mtime reflects local
   file activity, not the server's window boundaries).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

KST = timezone(timedelta(hours=9))

DEFAULT_LIMITS = {
    # Order-of-magnitude guesses, NOT published Anthropic quotas. See the
    # "_notes" field in token_gate_config.json for how these were chosen and
    # how to calibrate them for your own plan via `/usage`. These are only
    # used as a fallback if the config file is missing/unreadable.
    "session_limit": 1_500_000,
    "weekly_limit": 400_000_000,
    "fable_weekly_limit": 15_000_000,
}

HOLD_SESSION_THRESHOLD = 80.0
HOLD_WEEKLY_THRESHOLD = 90.0
HOLD_FABLE_THRESHOLD = 70.0

EXIT_OK = 0
EXIT_HOLD = 1
EXIT_UNKNOWN = 2


# --------------------------------------------------------------------------
# Pure helpers (unit-tested in test_token_gate.py)
# --------------------------------------------------------------------------

def parse_json_line(line: str) -> Optional[dict]:
    """Parse one JSONL line, returning None for blank/corrupt lines.

    Never raises -- corrupt lines are skipped per the error-tolerance
    requirement, not treated as fatal.
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def usage_total_tokens(usage: dict) -> int:
    """Sum the token-count fields of a usage object.

    Missing/None fields count as 0. Non-numeric junk is ignored defensively.
    """
    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        val = usage.get(key)
        if isinstance(val, (int, float)):
            total += val
    return int(total)


def is_fable_model(model: Optional[str]) -> bool:
    if not model or not isinstance(model, str):
        return False
    return "fable" in model.lower()


def parse_record_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse the top-level 'timestamp' field (ISO-8601, typically '...Z')."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        # Python's fromisoformat doesn't accept trailing 'Z' before 3.11;
        # normalize explicitly for broad compatibility.
        normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def extract_usage_record(obj: dict) -> Optional[tuple]:
    """Extract (message_id, model, usage_dict, timestamp) from a raw record.

    Returns None if this record is not an assistant/usage-bearing record.
    """
    if obj.get("type") != "assistant":
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    message_id = message.get("id")
    model = message.get("model")
    timestamp = parse_record_timestamp(obj.get("timestamp"))
    return (message_id, model, usage, timestamp)


def iter_usage_records(path: Path) -> Iterator[tuple]:
    """Stream-parse a JSONL transcript file, yielding usage-bearing records.

    Yields (message_id, model, usage_dict, timestamp). Corrupt lines and
    non-usage records are silently skipped (error tolerance requirement).
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                obj = parse_json_line(line)
                if obj is None:
                    continue
                rec = extract_usage_record(obj)
                if rec is not None:
                    yield rec
    except OSError:
        # File vanished / unreadable mid-scan -- skip the whole file.
        return


def sum_dedup_tokens(
    records: Iterable[tuple],
    seen_ids: set,
    predicate=None,
) -> int:
    """Sum usage_total_tokens over records, deduped by message_id.

    ``predicate(model, timestamp) -> bool`` optionally filters records
    (e.g. by time window or by fable model). Records with a falsy
    message_id are counted individually (never deduped) since there is no
    reliable dedup key for them.
    """
    total = 0
    for message_id, model, usage, timestamp in records:
        if predicate is not None and not predicate(model, timestamp):
            continue
        if message_id:
            if message_id in seen_ids:
                continue
            seen_ids.add(message_id)
        total += usage_total_tokens(usage)
    return total


def compute_verdict(session_pct: float, weekly_pct: float, fable_pct: float) -> str:
    if (
        session_pct >= HOLD_SESSION_THRESHOLD
        or weekly_pct >= HOLD_WEEKLY_THRESHOLD
        or fable_pct >= HOLD_FABLE_THRESHOLD
    ):
        return "HOLD"
    return "GO"


def pct(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


# --------------------------------------------------------------------------
# I/O-touching functions
# --------------------------------------------------------------------------

def default_transcript_root() -> Path:
    return Path.home() / ".claude" / "projects"


def find_transcript_files(root: Path) -> list:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(root.rglob("*.jsonl"))


def load_limits(config_path: Path) -> dict:
    """Load session/weekly/fable_weekly limits from JSON config.

    Falls back to DEFAULT_LIMITS (with a stderr warning) if the file is
    missing or malformed, so the tool still runs standalone.
    """
    limits = dict(DEFAULT_LIMITS)
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"token_gate: warning: could not load config {config_path} "
            f"({exc}); using built-in default limits.",
            file=sys.stderr,
        )
        return limits
    for key in ("session_limit", "weekly_limit", "fable_weekly_limit"):
        val = data.get(key)
        if isinstance(val, (int, float)) and val > 0:
            limits[key] = val
        else:
            print(
                f"token_gate: warning: config missing/invalid '{key}'; "
                f"using default {limits[key]}.",
                file=sys.stderr,
            )
    return limits


def checked_at_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def build_result(
    session_pct: Optional[float],
    weekly_pct: Optional[float],
    fable_weekly_pct: Optional[float],
    verdict: str,
) -> dict:
    return {
        "session_pct": session_pct,
        "weekly_pct": weekly_pct,
        "fable_weekly_pct": fable_weekly_pct,
        "verdict": verdict,
        "checked_at": checked_at_kst(),
    }


def run(root: Path, config_path: Path, now: Optional[datetime] = None) -> tuple:
    """Run the full gate computation.

    Returns (result_dict, exit_code). Does not print or exit -- kept pure
    for testability; main() handles I/O.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    files = find_transcript_files(root)
    if not root.exists():
        result = build_result(None, None, None, "UNKNOWN")
        return result, EXIT_UNKNOWN

    limits = load_limits(config_path)

    # -- Session: single most-recently-modified transcript file --
    session_total = 0
    if files:
        session_file = max(files, key=lambda p: p.stat().st_mtime)
        session_total = sum_dedup_tokens(
            iter_usage_records(session_file), seen_ids=set()
        )

    # -- Weekly: last 7 days across all transcript files, by record timestamp --
    cutoff = now - timedelta(days=7)

    def within_week(_model, timestamp):
        return timestamp is not None and timestamp >= cutoff

    def within_week_and_fable(model, timestamp):
        return within_week(model, timestamp) and is_fable_model(model)

    weekly_seen: set = set()
    fable_seen: set = set()
    weekly_total = 0
    fable_weekly_total = 0
    for path in files:
        # Materialize once per file so both predicates can scan it without
        # re-reading from disk twice.
        records = list(iter_usage_records(path))
        weekly_total += sum_dedup_tokens(records, weekly_seen, within_week)
        fable_weekly_total += sum_dedup_tokens(
            records, fable_seen, within_week_and_fable
        )

    session_pct = pct(session_total, limits["session_limit"])
    weekly_pct = pct(weekly_total, limits["weekly_limit"])
    fable_weekly_pct = pct(fable_weekly_total, limits["fable_weekly_limit"])

    verdict = compute_verdict(session_pct, weekly_pct, fable_weekly_pct)
    result = build_result(session_pct, weekly_pct, fable_weekly_pct, verdict)
    exit_code = EXIT_HOLD if verdict == "HOLD" else EXIT_OK
    return result, exit_code


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--transcripts-root",
        type=Path,
        default=default_transcript_root(),
        help="Root dir to scan for *.jsonl transcripts "
        "(default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "token_gate_config.json",
        help="Path to token_gate_config.json (default: alongside this script)",
    )
    args = parser.parse_args(argv)

    result, exit_code = run(args.transcripts_root, args.config)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
