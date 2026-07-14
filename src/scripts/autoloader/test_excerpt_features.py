"""excerpt_features.py 단위 테스트 — 순수 헬퍼만(librosa 미로드, 오디오 없음)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import excerpt_features as xf  # noqa: E402


class CenterExcerptTest(unittest.TestCase):
    def test_short_signal_returned_whole(self):
        y = np.arange(10, dtype=float)
        out = xf._center_excerpt(y, sr=1, sec=20.0)
        self.assertTrue((out == y).all())

    def test_center_window(self):
        y = np.arange(100, dtype=float)
        out = xf._center_excerpt(y, sr=1, sec=50.0)         # 창=50, 시작=(100-50)//2
        self.assertEqual(len(out), 50)
        self.assertEqual(out[0], 25.0)

    def test_matches_original_formula(self):
        sr, sec = 22050, 45.0
        y = np.zeros(int(sr * 200))
        out = xf._center_excerpt(y, sr, sec)
        self.assertEqual(len(out), int(sec * sr))


class R5Test(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual(xf.r5(0.123456789), 0.12346)

    def test_nan_becomes_empty(self):
        self.assertEqual(xf.r5(float("nan")), "")

    def test_int_passthrough(self):
        self.assertEqual(xf.r5(3), 3.0)


class ConstantsTest(unittest.TestCase):
    def test_frozen_extraction_params(self):
        """원본(genre_features_extract.py)과 달라지면 분포가 어긋난다 — 고정 검증."""
        self.assertEqual(xf.SR, 22050)
        self.assertEqual(xf.EXCERPT_SEC, 45.0)
        self.assertEqual(len(xf.KS_MAJ), 12)
        self.assertEqual(len(xf.KS_MIN), 12)
        self.assertEqual((xf.F0_MIN, xf.F0_MAX), (110.0, 1000.0))


if __name__ == "__main__":
    unittest.main()
