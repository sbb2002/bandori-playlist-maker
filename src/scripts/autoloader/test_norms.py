"""norms.py 단위 테스트 — 동결 z·energy_full 자기일관성·i_* 집계 산식."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import norms  # noqa: E402
from build_energy_full import GT_LOUD, GT_QUIET  # noqa: E402


def _feat_row(vals: dict, proxies: dict | None = None) -> dict:
    r = {c: str(v) for c, v in vals.items()}
    if proxies:
        r.update({c: str(v) for c, v in proxies.items()})
    return r


class ProxyNormsTest(unittest.TestCase):
    def _rows(self):
        base = [
            {"harmonic_ratio": 0.6, "flatness": 0.04, "voiced_frac_mix": 0.5,
             "rms": 0.25, "contrast": 20.0, "flux": 1.0},
            {"harmonic_ratio": 0.7, "flatness": 0.05, "voiced_frac_mix": 0.6,
             "rms": 0.30, "contrast": 22.0, "flux": 1.5},
            {"harmonic_ratio": 0.8, "flatness": 0.06, "voiced_frac_mix": 0.7,
             "rms": 0.35, "contrast": 24.0, "flux": 2.0},
        ]
        return [_feat_row(v) for v in base]

    def test_zscore_is_ddof1(self):
        rows = self._rows()
        n = norms.build_proxy_norms(rows)
        v = np.array([0.6, 0.7, 0.8])
        self.assertAlmostEqual(n["harmonic_ratio"]["mean"], v.mean(), places=12)
        self.assertAlmostEqual(n["harmonic_ratio"]["std"], v.std(ddof=1), places=12)

    def test_formulas(self):
        rows = self._rows()
        n = norms.build_proxy_norms(rows)
        got = norms.compute_proxies(rows[0], n)
        z = lambda col, x: (x - n[col]["mean"]) / n[col]["std"]  # noqa: E731
        self.assertAlmostEqual(got["acousticness_proxy"],
                               z("harmonic_ratio", 0.6) - z("flatness", 0.04))
        self.assertAlmostEqual(got["instrumentalness_proxy"],
                               -z("voiced_frac_mix", 0.5))
        self.assertAlmostEqual(got["energy_proxy"],
                               z("rms", 0.25) + z("contrast", 20.0) + z("flux", 1.0))

    def test_verify_roundtrip_zero_error(self):
        rows = self._rows()
        n = norms.build_proxy_norms(rows)
        for r in rows:
            r.update({k: repr(v) for k, v in norms.compute_proxies(r, n).items()})
        self.assertLess(norms.verify_proxy_norms(rows, n), 1e-12)


class EnergyFullFrozenTest(unittest.TestCase):
    """합성 분포에서 자기일관성(verify 100%)과 단조성만 확인한다."""

    def _fixture(self):
        quiet_idx = sorted(GT_QUIET)[:3]
        loud_idx = sorted(GT_LOUD)[:3]
        rows = [(idx, float(i))
                for i, idx in enumerate(quiet_idx + [1, 2, 3] + loud_idx)]
        master, feats = [], []
        for idx, level in rows:
            master.append({"idx": str(idx), "energy_full": ""})
            feats.append({"idx": str(idx), "band": "b", "error": "",
                          "cen_mean": str(1000 + 100 * level),
                          "perc_mean": str(0.2 + 0.05 * level),
                          "onset_mean": str(0.5 + 0.2 * level),
                          "zcr_mean": str(0.05 + 0.01 * level),
                          "flat_mean": str(0.01 + 0.005 * level),
                          "rms_p90": str(0.1 + 0.03 * level)})
        return master, feats

    def _write_feats(self, feats) -> Path:
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                        encoding="utf-8", newline="")
        cols = ["idx", "band", "cen_mean", "error", "perc_mean", "onset_mean",
                "zcr_mean", "flat_mean", "rms_p90"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(feats)
        f.close()
        return Path(f.name)

    def test_self_consistency_and_monotonic(self):
        master, feats = self._fixture()
        path = self._write_feats(feats)
        try:
            ef = norms.EnergyFullFrozen.build(path, {"b": True})
            # 저장값 = 재계산값으로 채우면 verify가 전행 exact여야 함
            for m in master:
                raw = next(x for x in feats if x["idx"] == m["idx"])
                m["energy_full"] = f"{ef.energy_full_for(raw):.6f}"
            ok, total, worst = ef.verify(master, path)
            self.assertEqual((ok, total), (len(master), len(master)))
            self.assertLess(worst, 5e-7)   # '%.6f' 저장 반올림 한계
            # 전 서브피처가 커질수록(=시끄러울수록) energy_full 단조 증가
            vals = [float(m["energy_full"]) for m in master]
            self.assertEqual(vals, sorted(vals))
            self.assertTrue(all(0.0 <= v <= 1.0 for v in vals))
        finally:
            path.unlink(missing_ok=True)

    def test_ineligible_band_excluded_from_pool(self):
        master, feats = self._fixture()
        for f in feats[-3:]:
            f["band"] = "tiny"                            # 풀 제외 대상
        path = self._write_feats(feats)
        try:
            ef = norms.EnergyFullFrozen.build(path, {"b": True, "tiny": False})
            self.assertEqual(len(ef._pool_sorted), len(feats) - 3)
        finally:
            path.unlink(missing_ok=True)


class ShapeNormsTest(unittest.TestCase):
    """형제 add_pulse_shape.py 채널 산식 이식 — ddof=0 z-score + neutral gap."""

    def _rows(self):
        base = [
            {"harmonic_ratio": 0.9, "centroid": 1000.0, "rolloff": 2000.0,
             "flatness": 0.01, "flux": 0.5, "zcr": 0.05},    # acoustic 극단
            {"harmonic_ratio": 0.3, "centroid": 6000.0, "rolloff": 9000.0,
             "flatness": 0.30, "flux": 1.0, "zcr": 0.40},    # bright 극단
            {"harmonic_ratio": 0.5, "centroid": 3000.0, "rolloff": 5000.0,
             "flatness": 0.10, "flux": 3.0, "zcr": 0.15},    # shimmer 극단
            {"harmonic_ratio": 0.55, "centroid": 3200.0, "rolloff": 5200.0,
             "flatness": 0.11, "flux": 1.1, "zcr": 0.16},    # neutral(뚜렷한 성분 없음)
        ]
        return [{k: str(v) for k, v in r.items()} | {"idx": str(i)}
                for i, r in enumerate(base)]

    def test_zscore_is_ddof0(self):
        rows = self._rows()
        n = norms.build_shape_norms(rows)
        v = np.array([0.9, 0.3, 0.5, 0.55])
        self.assertAlmostEqual(n["harmonic_ratio"]["mean"], v.mean(), places=12)
        self.assertAlmostEqual(n["harmonic_ratio"]["std"], v.std(ddof=0), places=12)

    def test_classifies_dominant_channel(self):
        rows = self._rows()
        n = norms.build_shape_norms(rows)
        self.assertEqual(norms.compute_shape(rows[0], n), "acoustic")
        self.assertEqual(norms.compute_shape(rows[1], n), "bright")
        self.assertEqual(norms.compute_shape(rows[2], n), "shimmer")
        self.assertEqual(norms.compute_shape(rows[3], n), "neutral")

    def test_verify_roundtrip_matches_stored_shape(self):
        rows = self._rows()
        n = norms.build_shape_norms(rows)
        audio_map_songs = [{"shape": norms.compute_shape(r, n)} for r in rows]
        ok, total = norms.verify_shape_norms(rows, n, audio_map_songs)
        self.assertEqual((ok, total), (len(rows), len(rows)))

    def test_missing_stored_shape_is_skipped_not_counted(self):
        rows = self._rows()
        n = norms.build_shape_norms(rows)
        audio_map_songs = [{"band": "x"} for _ in rows]   # 신곡 엔트리처럼 shape 없음
        ok, total = norms.verify_shape_norms(rows, n, audio_map_songs)
        self.assertEqual((ok, total), (0, 0))


class AggregateIntensityTest(unittest.TestCase):
    def test_formulas_and_format(self):
        n_frames = norms._SEG_FRAMES * 3
        frames = np.zeros((n_frames, 6), dtype=np.float32)
        frames[-norms._SEG_FRAMES:, :] = 2.0                # 끝 구간만 시끄러움
        med = np.zeros(6, dtype=np.float32)
        mad = np.ones(6, dtype=np.float32)
        got = norms.aggregate_intensity(frames, med, mad)
        self.assertEqual(got["i_start"], "0.00000")
        self.assertEqual(got["i_end"], "2.00000")
        self.assertEqual(got["i_min"], "0.00000")           # robust p5
        self.assertEqual(got["i_max"], "2.00000")           # robust p95
        self.assertAlmostEqual(float(got["i_mean"]), 2.0 / 3.0, places=4)

    def test_short_track_uses_whole_signal(self):
        frames = np.ones((10, 6), dtype=np.float32)
        got = norms.aggregate_intensity(frames, np.zeros(6, np.float32),
                                        np.ones(6, np.float32))
        self.assertEqual(got["i_start"], got["i_end"])


class BandAverageIntensityTest(unittest.TestCase):
    """soft-run이 intensity_norm 미준비 시 대체하는 밴드 평균 산식."""

    def _row(self, idx, band, i_mean):
        r = {"idx": str(idx), "band": band}
        for i, f in enumerate(norms.I_FIELDS):
            r[f] = f"{i_mean + i * 0.1:.5f}"
        return r

    def test_averages_only_same_band(self):
        rows = [self._row(1, "afterglow", 1.0), self._row(2, "afterglow", 3.0),
                self._row(3, "roselia", 9.0)]
        got = norms.band_average_intensity(rows, "afterglow")
        self.assertAlmostEqual(float(got["i_mean"]), 2.0, places=4)

    def test_excludes_given_idx(self):
        rows = [self._row(1, "afterglow", 1.0), self._row(2, "afterglow", 3.0)]
        got = norms.band_average_intensity(rows, "afterglow", exclude_idx=frozenset({2}))
        self.assertAlmostEqual(float(got["i_mean"]), 1.0, places=4)

    def test_no_reference_rows_returns_none(self):
        rows = [self._row(1, "roselia", 9.0)]
        self.assertIsNone(norms.band_average_intensity(rows, "afterglow"))

    def test_rows_with_blank_i_fields_are_skipped(self):
        blank = {"idx": "5", "band": "afterglow",
                 **{f: "" for f in norms.I_FIELDS}}
        rows = [blank, self._row(1, "afterglow", 2.0)]
        got = norms.band_average_intensity(rows, "afterglow")
        self.assertAlmostEqual(float(got["i_mean"]), 2.0, places=4)


if __name__ == "__main__":
    unittest.main()
