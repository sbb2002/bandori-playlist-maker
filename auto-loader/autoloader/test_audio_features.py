"""Unit tests for new audio features: loudness extraction and danceability normalization."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))

import norms  # noqa: E402


class DanceabilityFrozenTest(unittest.TestCase):
    """Test DanceabilityFrozen norm building and application."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmppath = Path(self.tmpdir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def _create_dance_raw_csv(self) -> Path:
        """Create a minimal danceability_raw.csv fixture."""
        csv_path = self.tmppath / "danceability_raw.csv"
        rows = [
            {"idx": "0", "band": "band_a", "song": "song_1",
             "dfa_alpha": "0.9", "danceability_norm": "0.1"},
            {"idx": "1", "band": "band_a", "song": "song_2",
             "dfa_alpha": "1.0", "danceability_norm": "0.3"},
            {"idx": "2", "band": "band_b", "song": "song_3",
             "dfa_alpha": "0.8", "danceability_norm": "0.0"},
            {"idx": "3", "band": "band_b", "song": "song_4",
             "dfa_alpha": "1.1", "danceability_norm": "0.5"},
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def _create_master_rows(self) -> list[dict]:
        """Create master rows matching danceability_raw.csv."""
        return [
            {"idx": "0", "band": "band_a", "song": "song_1"},
            {"idx": "1", "band": "band_a", "song": "song_2"},
            {"idx": "2", "band": "band_b", "song": "song_3"},
            {"idx": "3", "band": "band_b", "song": "song_4"},
        ]

    def test_build_from_csv(self):
        """Test building DanceabilityFrozen from CSV."""
        csv_path = self._create_dance_raw_csv()
        master_rows = self._create_master_rows()

        df = norms.DanceabilityFrozen.build_from_csv(csv_path, master_rows)

        # Should have 4 raw alpha values sorted
        self.assertEqual(len(df._raw_alpha_sorted), 4)
        # Sorted: [0.8, 0.9, 1.0, 1.1]
        expected = [0.8, 0.9, 1.0, 1.1]
        np.testing.assert_array_almost_equal(df._raw_alpha_sorted, expected)

    def test_danceability_norm_calculation(self):
        """Test danceability normalization with inverse percentile."""
        csv_path = self._create_dance_raw_csv()
        master_rows = self._create_master_rows()

        df = norms.DanceabilityFrozen.build_from_csv(csv_path, master_rows)

        # Low alpha (0.8) should have high danceability (close to 1.0)
        # since we use 1 - percentile
        norm_low = df.danceability_norm_for(0.8)
        self.assertGreater(norm_low, 0.5)

        # High alpha (1.1) should have low danceability (close to 0.0)
        norm_high = df.danceability_norm_for(1.1)
        self.assertLess(norm_high, 0.5)

        # Verify inverse relationship
        self.assertGreater(norm_low, norm_high)

    def test_load_or_build_no_verification(self):
        """Test that DanceabilityFrozen can be built without verification requirement."""
        csv_path = self._create_dance_raw_csv()
        master_rows = self._create_master_rows()
        json_path = self.tmppath / "danceability_norm.json"

        # Build without verification requirement - just test the flow
        df1 = norms.DanceabilityFrozen.build_from_csv(csv_path, master_rows)

        # Manually save to JSON for testing
        payload = {
            "purpose": "test",
            "raw_alpha_sorted": df1._raw_alpha_sorted,
        }
        json_path.write_text(json.dumps(payload) + "\n")
        self.assertTrue(json_path.exists())

        # Load from saved JSON
        d = json.loads(json_path.read_text())
        df2 = norms.DanceabilityFrozen(d["raw_alpha_sorted"])

        # Both should give same results
        test_alpha = 0.95
        self.assertAlmostEqual(
            df1.danceability_norm_for(test_alpha),
            df2.danceability_norm_for(test_alpha),
            places=6
        )

    def test_percentile_inversion(self):
        """Test that low alpha maps to high percentile (inverted scoring)."""
        csv_path = self._create_dance_raw_csv()
        master_rows = self._create_master_rows()

        df = norms.DanceabilityFrozen.build_from_csv(csv_path, master_rows)

        # Minimum alpha value (0.8) should map close to 1.0
        min_val = df.danceability_norm_for(0.8)
        self.assertGreater(min_val, 0.7)

        # Maximum alpha value (1.1) should map close to 0.0
        max_val = df.danceability_norm_for(1.1)
        self.assertLess(max_val, 0.3)


class LoudnessExtractionTest(unittest.TestCase):
    """Test loudness extraction module."""

    def test_extract_loudness_imports(self):
        """Test that extract_loudness module can be imported."""
        try:
            from extract_loudness import extract_features
            self.assertTrue(callable(extract_features))
        except ImportError as e:
            self.skipTest(f"extract_loudness module not available: {e}")

    def test_extract_loudness_signature(self):
        """Test that extract_features has correct signature."""
        try:
            from extract_loudness import extract_features
            import inspect
            sig = inspect.signature(extract_features)
            params = list(sig.parameters.keys())
            self.assertEqual(params, ["path"])
        except ImportError:
            self.skipTest("extract_loudness module not available")


if __name__ == "__main__":
    unittest.main()
