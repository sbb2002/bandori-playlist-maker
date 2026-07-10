#!/usr/bin/env python3
"""Unit tests for token_gate.py (standard library unittest only).

Run:
    python scripts/test_token_gate.py
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import token_gate as tg  # noqa: E402


def usage(input_tokens=0, output_tokens=0, cache_creation=0, cache_read=0):
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
    }


def assistant_record(message_id, model, usage_dict, timestamp_iso):
    return {
        "type": "assistant",
        "timestamp": timestamp_iso,
        "message": {"id": message_id, "model": model, "usage": usage_dict},
    }


class TestParseJsonLine(unittest.TestCase):
    def test_blank_line_returns_none(self):
        self.assertIsNone(tg.parse_json_line(""))
        self.assertIsNone(tg.parse_json_line("   \n"))

    def test_corrupt_json_returns_none(self):
        self.assertIsNone(tg.parse_json_line("{not valid json"))
        self.assertIsNone(tg.parse_json_line("{'single': 'quotes'}"))

    def test_non_object_json_returns_none(self):
        self.assertIsNone(tg.parse_json_line("[1, 2, 3]"))
        self.assertIsNone(tg.parse_json_line('"just a string"'))

    def test_valid_object_parses(self):
        self.assertEqual(tg.parse_json_line('{"a": 1}'), {"a": 1})


class TestUsageTotalTokens(unittest.TestCase):
    def test_sums_all_four_fields(self):
        u = usage(input_tokens=10, output_tokens=5, cache_creation=100, cache_read=50)
        self.assertEqual(tg.usage_total_tokens(u), 165)

    def test_missing_fields_count_as_zero(self):
        self.assertEqual(tg.usage_total_tokens({"input_tokens": 7}), 7)
        self.assertEqual(tg.usage_total_tokens({}), 0)

    def test_non_numeric_field_ignored(self):
        u = {"input_tokens": 10, "output_tokens": None, "cache_creation_input_tokens": "n/a"}
        self.assertEqual(tg.usage_total_tokens(u), 10)


class TestIsFableModel(unittest.TestCase):
    def test_matches_fable_variants(self):
        self.assertTrue(tg.is_fable_model("claude-fable-5"))
        self.assertTrue(tg.is_fable_model("Claude-Fable-5"))

    def test_rejects_non_fable(self):
        self.assertFalse(tg.is_fable_model("claude-sonnet-5"))
        self.assertFalse(tg.is_fable_model("<synthetic>"))
        self.assertFalse(tg.is_fable_model(None))
        self.assertFalse(tg.is_fable_model(""))


class TestParseRecordTimestamp(unittest.TestCase):
    def test_parses_z_suffix_as_utc(self):
        dt = tg.parse_record_timestamp("2026-07-10T04:19:34.791Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 7)
        self.assertEqual(dt.day, 10)

    def test_none_or_missing_returns_none(self):
        self.assertIsNone(tg.parse_record_timestamp(None))
        self.assertIsNone(tg.parse_record_timestamp(""))

    def test_malformed_returns_none(self):
        self.assertIsNone(tg.parse_record_timestamp("not-a-date"))


class TestExtractUsageRecord(unittest.TestCase):
    def test_extracts_from_assistant_record(self):
        rec = assistant_record(
            "msg_1", "claude-sonnet-5", usage(input_tokens=1, output_tokens=2),
            "2026-07-10T04:19:34.791Z",
        )
        result = tg.extract_usage_record(rec)
        self.assertIsNotNone(result)
        message_id, model, usage_dict, ts = result
        self.assertEqual(message_id, "msg_1")
        self.assertEqual(model, "claude-sonnet-5")
        self.assertEqual(usage_dict["input_tokens"], 1)
        self.assertIsNotNone(ts)

    def test_non_assistant_type_returns_none(self):
        rec = {"type": "user", "message": {"usage": usage()}}
        self.assertIsNone(tg.extract_usage_record(rec))

    def test_assistant_without_usage_returns_none(self):
        rec = {"type": "assistant", "message": {"model": "claude-sonnet-5"}}
        self.assertIsNone(tg.extract_usage_record(rec))

    def test_assistant_without_message_returns_none(self):
        rec = {"type": "assistant"}
        self.assertIsNone(tg.extract_usage_record(rec))


class TestSumDedupTokens(unittest.TestCase):
    def test_dedupes_repeated_message_id(self):
        # Simulates one API response split across two content-block lines
        # (thinking + tool_use), both carrying the identical usage object --
        # the real-world scenario observed in actual transcripts.
        u = usage(input_tokens=100, output_tokens=50)
        records = [
            ("msg_1", "claude-sonnet-5", u, None),
            ("msg_1", "claude-sonnet-5", u, None),
        ]
        total = tg.sum_dedup_tokens(records, seen_ids=set())
        self.assertEqual(total, 150)  # counted once, not twice

    def test_distinct_message_ids_both_counted(self):
        records = [
            ("msg_1", "claude-sonnet-5", usage(input_tokens=100), None),
            ("msg_2", "claude-sonnet-5", usage(input_tokens=200), None),
        ]
        total = tg.sum_dedup_tokens(records, seen_ids=set())
        self.assertEqual(total, 300)

    def test_predicate_filters_records(self):
        records = [
            ("msg_1", "claude-fable-5", usage(input_tokens=100), None),
            ("msg_2", "claude-sonnet-5", usage(input_tokens=200), None),
        ]
        total = tg.sum_dedup_tokens(
            records, seen_ids=set(), predicate=lambda m, t: tg.is_fable_model(m)
        )
        self.assertEqual(total, 100)

    def test_records_without_message_id_never_deduped(self):
        u = usage(input_tokens=10)
        records = [(None, "claude-sonnet-5", u, None)] * 3
        total = tg.sum_dedup_tokens(records, seen_ids=set())
        self.assertEqual(total, 30)

    def test_shared_seen_set_dedupes_across_calls(self):
        seen = set()
        u = usage(input_tokens=10)
        first = tg.sum_dedup_tokens([("msg_1", "m", u, None)], seen)
        second = tg.sum_dedup_tokens([("msg_1", "m", u, None)], seen)
        self.assertEqual(first, 10)
        self.assertEqual(second, 0)


class TestComputeVerdict(unittest.TestCase):
    def test_go_when_all_below_thresholds(self):
        self.assertEqual(tg.compute_verdict(10, 10, 10), "GO")

    def test_hold_on_session_threshold(self):
        self.assertEqual(tg.compute_verdict(80, 0, 0), "HOLD")
        self.assertEqual(tg.compute_verdict(79.9, 0, 0), "GO")

    def test_hold_on_weekly_threshold(self):
        self.assertEqual(tg.compute_verdict(0, 90, 0), "HOLD")
        self.assertEqual(tg.compute_verdict(0, 89.9, 0), "GO")

    def test_hold_on_fable_threshold(self):
        self.assertEqual(tg.compute_verdict(0, 0, 70), "HOLD")
        self.assertEqual(tg.compute_verdict(0, 0, 69.9), "GO")


class TestPct(unittest.TestCase):
    def test_normal_division(self):
        self.assertEqual(tg.pct(50, 100), 50.0)

    def test_zero_denominator_returns_zero(self):
        self.assertEqual(tg.pct(50, 0), 0.0)

    def test_rounds_to_one_decimal(self):
        self.assertEqual(tg.pct(1, 3), 33.3)


class TestIterUsageRecordsFile(unittest.TestCase):
    def test_skips_corrupt_lines_and_reads_valid_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            lines = [
                json.dumps(assistant_record(
                    "msg_1", "claude-sonnet-5", usage(input_tokens=10),
                    "2026-07-10T00:00:00Z",
                )),
                "{this is not json",
                "",
                json.dumps({"type": "user", "message": {"role": "user"}}),
                json.dumps(assistant_record(
                    "msg_2", "claude-sonnet-5", usage(input_tokens=20),
                    "2026-07-10T00:00:01Z",
                )),
            ]
            path.write_text("\n".join(lines), encoding="utf-8")
            records = list(tg.iter_usage_records(path))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0][0], "msg_1")
            self.assertEqual(records[1][0], "msg_2")

    def test_missing_file_yields_nothing(self):
        records = list(tg.iter_usage_records(Path("does-not-exist.jsonl")))
        self.assertEqual(records, [])


class TestRunIntegration(unittest.TestCase):
    """End-to-end test against a synthetic transcript tree, no real
    ~/.claude/projects data touched."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name) / "projects"
        self.root.mkdir()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.config_path.write_text(json.dumps({
            "session_limit": 1000,
            "weekly_limit": 2000,
            "fable_weekly_limit": 500,
        }), encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, relpath, records):
        p = self.root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return p

    def test_unknown_when_root_missing(self):
        missing_root = self.root / "nope"
        result, exit_code = tg.run(missing_root, self.config_path)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(exit_code, tg.EXIT_UNKNOWN)

    def test_go_verdict_with_low_usage(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write("proj/session.jsonl", [
            assistant_record("msg_1", "claude-sonnet-5", usage(input_tokens=100), recent),
        ])
        result, exit_code = tg.run(self.root, self.config_path, now=now)
        self.assertEqual(result["verdict"], "GO")
        self.assertEqual(exit_code, tg.EXIT_OK)
        self.assertEqual(result["session_pct"], 10.0)  # 100/1000

    def test_hold_verdict_when_session_over_threshold(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write("proj/session.jsonl", [
            assistant_record("msg_1", "claude-sonnet-5", usage(input_tokens=900), recent),
        ])
        result, exit_code = tg.run(self.root, self.config_path, now=now)
        self.assertEqual(result["session_pct"], 90.0)  # 900/1000 >= 80
        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(exit_code, tg.EXIT_HOLD)

    def test_weekly_window_excludes_old_records(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        old = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write("proj/session.jsonl", [
            assistant_record("msg_old", "claude-sonnet-5", usage(input_tokens=1000), old),
            assistant_record("msg_new", "claude-sonnet-5", usage(input_tokens=200), recent),
        ])
        result, _ = tg.run(self.root, self.config_path, now=now)
        # weekly_limit=2000; only the recent 200-token record should count.
        self.assertEqual(result["weekly_pct"], 10.0)

    def test_duplicate_content_block_lines_not_double_counted(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        u = usage(input_tokens=500)
        # Same message.id twice, as happens when one API response is split
        # into a thinking block + a tool_use block in real transcripts.
        self._write("proj/session.jsonl", [
            assistant_record("msg_1", "claude-sonnet-5", u, recent),
            assistant_record("msg_1", "claude-sonnet-5", u, recent),
        ])
        result, _ = tg.run(self.root, self.config_path, now=now)
        self.assertEqual(result["session_pct"], 50.0)  # 500/1000, not 1000/1000

    def test_fable_weekly_isolated_from_regular_weekly(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write("proj/session.jsonl", [
            assistant_record("msg_1", "claude-fable-5", usage(input_tokens=250), recent),
            assistant_record("msg_2", "claude-sonnet-5", usage(input_tokens=250), recent),
        ])
        result, _ = tg.run(self.root, self.config_path, now=now)
        self.assertEqual(result["fable_weekly_pct"], 50.0)  # 250/500
        self.assertEqual(result["weekly_pct"], 25.0)  # (250+250)/2000

    def test_session_is_most_recently_modified_file_only(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_file = self._write("proj/old.jsonl", [
            assistant_record("msg_old", "claude-sonnet-5", usage(input_tokens=900), recent),
        ])
        new_file = self._write("proj/new.jsonl", [
            assistant_record("msg_new", "claude-sonnet-5", usage(input_tokens=100), recent),
        ])
        # Force new_file to have a strictly later mtime than old_file.
        import os
        import time
        old_stat = old_file.stat()
        os.utime(old_file, (old_stat.st_atime, old_stat.st_mtime - 100))
        result, _ = tg.run(self.root, self.config_path, now=now)
        # Only new_file's 100 tokens count toward session (limit 1000 -> 10%),
        # even though old.jsonl has more tokens and both are within the week.
        self.assertEqual(result["session_pct"], 10.0)
        self.assertEqual(result["weekly_pct"], 50.0)  # (900+100)/2000

    def test_corrupt_line_does_not_crash_run(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        p = self.root / "proj" / "session.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        good = json.dumps(assistant_record(
            "msg_1", "claude-sonnet-5", usage(input_tokens=100), recent
        ))
        p.write_text(good + "\n{broken json here\n" + good.replace("msg_1", "msg_2"),
                      encoding="utf-8")
        result, exit_code = tg.run(self.root, self.config_path, now=now)
        self.assertIn(result["verdict"], ("GO", "HOLD"))
        self.assertNotEqual(result["verdict"], "UNKNOWN")

    def test_missing_config_falls_back_to_defaults(self):
        now = datetime(2026, 7, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write("proj/session.jsonl", [
            assistant_record("msg_1", "claude-sonnet-5", usage(input_tokens=100), recent),
        ])
        missing_config = Path(self.tmpdir.name) / "no_such_config.json"
        result, exit_code = tg.run(self.root, missing_config, now=now)
        # Should not crash; falls back to DEFAULT_LIMITS.
        self.assertIn(result["verdict"], ("GO", "HOLD"))
        expected_pct = tg.pct(100, tg.DEFAULT_LIMITS["session_limit"])
        self.assertEqual(result["session_pct"], expected_pct)


class TestCheckedAtFormat(unittest.TestCase):
    def test_has_kst_offset(self):
        ts = tg.checked_at_kst()
        self.assertTrue(ts.endswith("+09:00"))
        # Must be parseable as ISO8601.
        parsed = datetime.fromisoformat(ts)
        self.assertEqual(parsed.utcoffset(), timedelta(hours=9))


if __name__ == "__main__":
    unittest.main()
