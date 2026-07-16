"""Unit tests for scripts/data/video_id.py.

Run with:
    python -m unittest scripts.data.test_video_id -v
or (from this directory):
    python test_video_id.py
"""

import csv
import os
import unittest

from video_id import extract_video_id


class TestExtractVideoIdNormalCases(unittest.TestCase):
    def test_youtu_be_basic(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/09B-WljIiTo"), "09B-WljIiTo"
        )

    def test_youtu_be_with_query_param(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/dQw4w9WgXcQ?si=abcDEF12345"),
            "dQw4w9WgXcQ",
        )

    def test_youtube_com_watch(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_youtube_com_watch_extra_params(self):
        self.assertEqual(
            extract_video_id(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=2"
            ),
            "dQw4w9WgXcQ",
        )

    def test_youtube_com_no_www(self):
        self.assertEqual(
            extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_m_youtube_com(self):
        self.assertEqual(
            extract_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_youtube_com_embed(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_video_id_allows_underscore_and_hyphen(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/_lfuqSepLNw"), "_lfuqSepLNw"
        )
        self.assertEqual(
            extract_video_id("https://youtu.be/q-TEDPBUv7M"), "q-TEDPBUv7M"
        )

    def test_leading_trailing_whitespace_stripped(self):
        self.assertEqual(
            extract_video_id("  https://youtu.be/09B-WljIiTo  "), "09B-WljIiTo"
        )


class TestExtractVideoIdEdgeCases(unittest.TestCase):
    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("   ")

    def test_none_raises_value_error_not_type_error(self):
        with self.assertRaises(ValueError):
            extract_video_id(None)  # type: ignore[arg-type]

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            extract_video_id(12345)  # type: ignore[arg-type]

    def test_not_youtube_url_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://example.com/watch?v=dQw4w9WgXcQ")

    def test_not_a_url_at_all_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("not a url at all")

    def test_id_too_short_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://youtu.be/short")

    def test_id_too_long_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://youtu.be/dQw4w9WgXcQextra")

    def test_youtu_be_with_no_path_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://youtu.be/")

    def test_youtube_com_watch_missing_v_param_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://www.youtube.com/watch?list=PL123")

    def test_youtube_com_unrecognized_path_raises(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://www.youtube.com/results?search_query=x")

    def test_never_returns_none(self):
        # Every raised case above must be a ValueError, never a None return.
        # This test documents the contract explicitly for a mix of bad inputs.
        bad_inputs = ["", None, 42, "https://example.com/x", "https://youtu.be/x"]
        for bad in bad_inputs:
            with self.assertRaises(ValueError):
                result = extract_video_id(bad)  # type: ignore[arg-type]
                # If no exception were raised, this assertion would catch a
                # silent None return instead of masking it as a passing test.
                self.assertIsNotNone(result)


class TestAgainstSongsFullCsv(unittest.TestCase):
    """Integration check against the real 660-row source CSV (read-only)."""

    CSV_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "bandori-song-sorter",
        "src",
        "content",
        "cluster",
        "songs_full.csv",
    )

    @classmethod
    def setUpClass(cls):
        cls.csv_path = os.path.normpath(cls.CSV_PATH)

    def test_all_urls_extract_11_char_ids(self):
        if not os.path.exists(self.csv_path):
            self.skipTest(f"songs_full.csv not found at {self.csv_path}")

        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 660, "expected exactly 660 data rows")

        ids = []
        for row in rows:
            vid = extract_video_id(row["url"])
            self.assertEqual(len(vid), 11)
            ids.append(vid)

        self.assertEqual(len(ids), 660)
        # Report-only info (unique count asserted to be <= total, and
        # printed for the human-readable report step run separately).
        self.assertLessEqual(len(set(ids)), len(ids))


if __name__ == "__main__":
    unittest.main()
