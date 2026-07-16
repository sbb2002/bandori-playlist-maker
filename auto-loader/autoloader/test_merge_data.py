"""merge_data.py 단위 테스트 — append 불변성·검증·실패 롤백(원자성)."""
from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import merge_data  # noqa: E402

MASTER_HEADER = ("idx,band,song,url,video_id,key,camelot,tempo_excerpt,energy_proxy,"
                 "mode_score,acousticness_proxy,instrumentalness_proxy,bpm,energy,shape,"
                 "eligible_band,energy_full,i_mean,i_std,i_max,i_min,i_start,i_end")


def _landed(idx: int, band: str = "mygo", vid: str = "NEWVID00000") -> dict:
    return {
        "cand": {"idx": idx, "band": band, "song": f"신곡{idx}",
                 "url": f"https://youtu.be/{vid}", "video_id": vid},
        "excerpt": {"duration_s": 200.0, "harmonic_ratio": 0.5, "centroid": 2500.0,
                    "rolloff": 5000.0, "flatness": 0.04, "contrast": 21.0,
                    "flux": 1.2, "zcr": 0.15, "rms": 0.27,
                    "tempo_excerpt": 120.0, "mode_score": 0.1, "key": "Amaj",
                    "voiced_frac_mix": 0.5},
        "proxies": {"acousticness_proxy": -1.0, "instrumentalness_proxy": -0.5,
                    "energy_proxy": 0.3},
        "full_feats": {"duration_sec": 200.0, "cen_mean": 2500.0, "cen_p90": 3000.0,
                       "roll_mean": 5000.0, "roll_p90": 6000.0, "bw_mean": 2000.0,
                       "bw_p90": 2500.0, "flat_mean": 0.04, "flat_p90": 0.08,
                       "contrast_mean": 21.0, "contrast_p90": 24.0,
                       "zcr_mean": 0.15, "zcr_p90": 0.2, "perc_mean": 0.4,
                       "perc_p90": 0.6, "perc_p95": 0.7, "onset_mean": 1.2,
                       "onset_p90": 2.0, "onset_rate": 3.0, "rms_mean": 0.27,
                       "rms_p90": 0.35, "extract_sec": 1.0},
        "audio_entry": {"band": band, "song": f"신곡{idx}", "bpm": 120.0,
                        "energy": 0.5},
        "shape": "neutral",
        "energy_full": 0.75,
        "intensity": {"i_mean": "0.10000", "i_std": "0.50000", "i_max": "1.00000",
                      "i_min": "-0.50000", "i_start": "0.00000", "i_end": "0.20000"},
    }


class AssembleRowTest(unittest.TestCase):
    def test_row_shape_and_format(self):
        s = _landed(660)
        row = merge_data.assemble_master_row(
            s["cand"], s["excerpt"], s["proxies"], s["audio_entry"],
            s["energy_full"], s["intensity"], True, s["shape"])
        self.assertEqual(row["idx"], 660)
        self.assertEqual(row["key"], "Amaj")
        self.assertTrue(row["camelot"])                    # camelot.py 매핑 성공
        self.assertEqual(row["energy_full"], "0.750000")   # %.6f
        self.assertEqual(row["i_mean"], "0.10000")         # %.5f 유지
        self.assertIs(row["eligible_band"], True)          # csv에서 'True'로 직렬화
        self.assertEqual(row["shape"], "neutral")          # audio_entry가 아닌 상류 계산값

    def test_column_set_matches_master_header(self):
        s = _landed(660)
        row = merge_data.assemble_master_row(
            s["cand"], s["excerpt"], s["proxies"], s["audio_entry"],
            s["energy_full"], s["intensity"], False, s["shape"])
        self.assertEqual(set(row), set(MASTER_HEADER.split(",")))

    def test_missing_energy_key_defaults_to_blank(self):
        """형제 audio_map 신곡 엔트리에는 energy 키가 없다(2026-07-15 확인) —
        KeyError 없이 공란으로 처리돼야 한다(song_repo 비소비 레거시 컬럼)."""
        s = _landed(660)
        s["audio_entry"] = {"band": "mygo", "song": "신곡660", "bpm": 120.0}
        row = merge_data.assemble_master_row(
            s["cand"], s["excerpt"], s["proxies"], s["audio_entry"],
            s["energy_full"], s["intensity"], True, s["shape"])
        self.assertEqual(row["energy"], "")
        self.assertEqual(row["bpm"], 120.0)


class BandEligibilityTest(unittest.TestCase):
    def test_no_band_excluded_regardless_of_sample_size(self):
        """B1 정책(n<10 제외) 폐기(2026-07-15) — 표본이 적어도 항상 eligible."""
        rows = [{"band": "big"}] * 10 + [{"band": "tiny"}] * 1
        elig = merge_data.band_eligibility(rows)
        self.assertTrue(elig["big"])
        self.assertTrue(elig["tiny"])


class MergeTest(unittest.TestCase):
    """임시 repo_root에 미니 data/를 만들어 merge 전체 경로를 검증."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        data = self.root / "data"
        data.mkdir()
        # master 2행(mygo 10곡 밴드로 취급되도록 songs_full mirror에 채움)
        master_rows = [
            "0,mygo,old0,https://youtu.be/OLDVID00000,OLDVID00000,Amaj,11B,120.0,"
            "0.1,0.2,-1.0,-0.5,120.0,0.5,neutral,True,0.500000,"
            "0.10000,0.50000,1.00000,-0.50000,0.00000,0.20000",
            "1,mygo,old1,https://youtu.be/OLDVID00001,OLDVID00001,Dmaj,10B,110.0,"
            "0.1,0.2,-1.0,-0.5,110.0,0.4,neutral,True,0.400000,"
            "0.10000,0.50000,1.00000,-0.50000,0.00000,0.20000",
        ]
        (data / "songs_master.csv").write_bytes(
            (MASTER_HEADER + "\r\n" + "\r\n".join(master_rows) + "\r\n").encode())
        (data / "song_features_with_proxies.csv").write_bytes(
            b"band,idx,song,duration_s,harmonic_ratio,centroid,rolloff,flatness,"
            b"contrast,flux,zcr,rms,tempo_excerpt,mode_score,key,voiced_frac_mix,"
            b"acousticness_proxy,instrumentalness_proxy,energy_proxy\r\n")
        cols = ["idx", "band", "song", "duration_sec", "cen_mean", "cen_p90",
                "roll_mean", "roll_p90", "bw_mean", "bw_p90", "flat_mean", "flat_p90",
                "contrast_mean", "contrast_p90", "zcr_mean", "zcr_p90", "perc_mean",
                "perc_p90", "perc_p95", "onset_mean", "onset_p90", "onset_rate",
                "rms_mean", "rms_p90", "extract_sec", "error"]
        (data / "full_audio_features.csv").write_bytes(
            (",".join(cols) + "\r\n").encode())
        (data / "temporal_intensity.csv").write_bytes(
            b"idx,band,song,i_mean,i_std,i_max,i_min,i_start,i_end\r\n")
        (data / "songs_full.csv").write_bytes(b"idx,band,song,url\r\n")
        (data / "audio_map.json").write_bytes(b"{}")

        # mirror 소스: mygo 10곡 + 신곡 1곡 → eligible 유지
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(["idx", "band", "song", "url"])
        for i in range(10):
            w.writerow([i, "mygo", f"old{i}", f"https://youtu.be/OLDVID{i:05d}"])
        w.writerow([660, "mygo", "신곡660", "https://youtu.be/NEWVID00000"])
        self.sf_bytes = buf.getvalue().encode()
        self.am_bytes = json.dumps({"songs": []}).encode()

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()

    def test_merge_appends_and_preserves_existing(self):
        before_master = self._read("data/songs_master.csv")
        merge_data.merge(self.root, [_landed(660)], self.sf_bytes, self.am_bytes)
        after = self._read("data/songs_master.csv")
        self.assertTrue(after.startswith(before_master))   # 기존 행 바이트 불변
        rows = list(csv.DictReader(
            (self.root / "data/songs_master.csv").open(encoding="utf-8", newline="")))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["video_id"], "NEWVID00000")
        self.assertEqual(rows[-1]["eligible_band"], "True")
        self.assertEqual(self._read("data/songs_full.csv"), self.sf_bytes)  # mirror

    def test_duplicate_video_id_rolls_back_everything(self):
        snapshots = {rel: self._read(rel) for rel in merge_data.ALL_TARGETS}
        dup = _landed(661, vid="OLDVID00000")               # 이미 master에 존재
        with self.assertRaises(AssertionError):
            merge_data.merge(self.root, [dup], self.sf_bytes, self.am_bytes)
        for rel, before in snapshots.items():
            self.assertEqual(self._read(rel), before, f"롤백 실패: {rel}")

    def test_partial_write_failure_rolls_back_everything(self):
        """mirror·일부 append가 이미 기록된 뒤 실패해도 전 파일이 복원돼야 한다."""
        snapshots = {rel: self._read(rel) for rel in merge_data.ALL_TARGETS}
        bad = _landed(660)
        bad["excerpt"]["key"] = "Zmaj"                      # camelot 매핑 불가 → 중간 실패
        with self.assertRaises(Exception):
            merge_data.merge(self.root, [bad], self.sf_bytes, self.am_bytes)
        for rel, before in snapshots.items():
            self.assertEqual(self._read(rel), before, f"롤백 실패: {rel}")

    def test_appended_file_gets_missing_trailing_newline(self):
        p = self.root / "data/temporal_intensity.csv"
        p.write_bytes(p.read_bytes().rstrip(b"\r\n"))       # 말미 개행 제거
        merge_data.merge(self.root, [_landed(660)], self.sf_bytes, self.am_bytes)
        rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["i_mean"], "0.10000")


class PatchIntensityRowsTest(unittest.TestCase):
    """soft-run이 밴드 평균으로 임시 대체했던 i_*를 되짚어 갱신(백필)하는 경로."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        data = self.root / "data"
        data.mkdir()
        master_rows = [
            "0,mygo,old0,https://youtu.be/OLDVID00000,OLDVID00000,Amaj,11B,120.0,"
            "0.1,0.2,-1.0,-0.5,120.0,0.5,neutral,True,0.500000,"
            "0.10000,0.50000,1.00000,-0.50000,0.00000,0.20000",
            "660,mygo,신곡660,https://youtu.be/NEWVID00000,NEWVID00000,Amaj,11B,120.0,"
            "0.1,0.2,-1.0,-0.5,120.0,,neutral,True,0.750000,"
            "0.10000,0.50000,1.00000,-0.50000,0.00000,0.20000",   # provisional(밴드 평균)
        ]
        (data / "songs_master.csv").write_bytes(
            (MASTER_HEADER + "\r\n" + "\r\n".join(master_rows) + "\r\n").encode())
        (data / "temporal_intensity.csv").write_bytes(
            b"idx,band,song,i_mean,i_std,i_max,i_min,i_start,i_end\r\n"
            b"0,mygo,old0,0.10000,0.50000,1.00000,-0.50000,0.00000,0.20000\r\n"
            b"660,mygo,\xec\x8b\xa0\xea\xb3\xa1660,0.10000,0.50000,1.00000,"
            b"-0.50000,0.00000,0.20000\r\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_patches_only_target_idx_i_fields(self):
        before_master = (self.root / "data/songs_master.csv").read_bytes()
        real = {"i_mean": "0.42000", "i_std": "0.11000", "i_max": "0.90000",
               "i_min": "0.05000", "i_start": "0.30000", "i_end": "0.55000"}
        merge_data.patch_intensity_rows(self.root, {660: real})

        rows = list(csv.DictReader(
            (self.root / "data/songs_master.csv").open(encoding="utf-8", newline="")))
        self.assertEqual(rows[0]["i_mean"], "0.10000")      # idx=0 불변
        self.assertEqual(rows[1]["i_mean"], "0.42000")      # idx=660 갱신
        self.assertEqual(rows[1]["idx"], "660")
        self.assertEqual(rows[1]["key"], "Amaj")            # i_* 외 컬럼 불변
        self.assertNotEqual((self.root / "data/songs_master.csv").read_bytes(),
                            before_master)

        trows = list(csv.DictReader(
            (self.root / "data/temporal_intensity.csv").open(encoding="utf-8", newline="")))
        self.assertEqual(trows[1]["i_mean"], "0.42000")

    def test_no_updates_is_noop(self):
        before = (self.root / "data/songs_master.csv").read_bytes()
        merge_data.patch_intensity_rows(self.root, {})
        self.assertEqual((self.root / "data/songs_master.csv").read_bytes(), before)

    def test_unknown_idx_rolls_back(self):
        before_master = (self.root / "data/songs_master.csv").read_bytes()
        before_temporal = (self.root / "data/temporal_intensity.csv").read_bytes()
        with self.assertRaises(AssertionError):
            merge_data.patch_intensity_rows(self.root, {999: {"i_mean": "0.0"}})
        self.assertEqual((self.root / "data/songs_master.csv").read_bytes(), before_master)
        self.assertEqual((self.root / "data/temporal_intensity.csv").read_bytes(),
                         before_temporal)


if __name__ == "__main__":
    unittest.main()
