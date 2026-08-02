"""enrich_heavy_feats.py의 CSV 부분-패치 로직 단위 테스트.

essentia/torch 없이도 동작하는 CSV 패치 함수만 테스트 가능.
"""
import csv
import tempfile
import unittest
from pathlib import Path
import sys

# enrich_heavy_feats 모듈 임포트
sys.path.insert(0, str(Path(__file__).parent))
import enrich_heavy_feats as efx


class TestPatchCSV(unittest.TestCase):
    """CSV 부분-패치 로직 테스트."""

    def setUp(self):
        """테스트용 임시 CSV 파일 생성."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.tmpdir.name) / "test_songs_master.csv"

        # 테스트 데이터: 3행
        rows = [
            {
                "idx": "0",
                "band": "poppin_party",
                "song": "Song A",
                "m6-valence_median": "0.5",
                "m9-instr_stem_ratio": "0.3",
                "m11-speech_median": "0.2",
            },
            {
                "idx": "1",
                "band": "roselia",
                "song": "Song B",
                "m6-valence_median": "",  # 빈 값
                "m9-instr_stem_ratio": "0.4",
                "m11-speech_median": "0.25",
            },
            {
                "idx": "2",
                "band": "raise_a_suilen",
                "song": "Song C",
                "m6-valence_median": "0.6",
                "m9-instr_stem_ratio": "",
                "m11-speech_median": "",
            },
        ]

        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = ["idx", "band", "song", "m6-valence_median", "m9-instr_stem_ratio", "m11-speech_median"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # 원본 바이트 저장 (검증용)
        self.original_bytes = self.csv_path.read_bytes()

    def tearDown(self):
        """임시 파일 정리."""
        self.tmpdir.cleanup()

    def test_patch_single_column(self):
        """단일 컬럼 갱신 테스트."""
        # 모듈의 _MASTER_CSV를 임시 파일로 교체
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            # idx=1의 m6-valence_median을 0.7로 갱신
            updates = {1: {"m6-valence_median": "0.7"}}
            result = efx.patch_csv(updates)

            self.assertTrue(result, "patch_csv should return True on success")

            # 파일 재읽기
            with self.csv_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            # idx=1 검증
            row_1 = [r for r in rows if r["idx"] == "1"][0]
            self.assertEqual(row_1["m6-valence_median"], "0.7", "m6 값이 갱신되어야 함")
            self.assertEqual(row_1["m9-instr_stem_ratio"], "0.4", "m9 값은 불변")

            # 다른 행 검증 (불변성)
            row_0 = [r for r in rows if r["idx"] == "0"][0]
            self.assertEqual(row_0["m6-valence_median"], "0.5")
            self.assertEqual(row_0["band"], "poppin_party")

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_multiple_columns(self):
        """다중 컬럼 갱신 테스트."""
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            # idx=2의 m9/m11 갱신
            updates = {
                2: {
                    "m9-instr_stem_ratio": "0.5",
                    "m11-speech_median": "0.35",
                }
            }
            result = efx.patch_csv(updates)
            self.assertTrue(result)

            # 검증
            with self.csv_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            row_2 = [r for r in rows if r["idx"] == "2"][0]
            self.assertEqual(row_2["m9-instr_stem_ratio"], "0.5")
            self.assertEqual(row_2["m11-speech_median"], "0.35")
            self.assertEqual(row_2["m6-valence_median"], "0.6")  # 불변

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_multiple_rows(self):
        """여러 행 동시 갱신 테스트."""
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            updates = {
                0: {"m6-valence_median": "0.55"},
                1: {"m6-valence_median": "0.75"},
                2: {"m11-speech_median": "0.4"},
            }
            result = efx.patch_csv(updates)
            self.assertTrue(result)

            with self.csv_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(len(rows), 3)
            row_0 = [r for r in rows if r["idx"] == "0"][0]
            row_1 = [r for r in rows if r["idx"] == "1"][0]
            row_2 = [r for r in rows if r["idx"] == "2"][0]

            self.assertEqual(row_0["m6-valence_median"], "0.55")
            self.assertEqual(row_1["m6-valence_median"], "0.75")
            self.assertEqual(row_2["m11-speech_median"], "0.4")

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_with_missing_idx(self):
        """존재하지 않는 idx 갱신 시도 (롤백 테스트)."""
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            # idx=999는 파일에 없음
            updates = {999: {"m6-valence_median": "0.9"}}
            result = efx.patch_csv(updates)

            self.assertFalse(result, "patch_csv should return False on missing idx")

            # 파일이 원본 상태로 복원되었는지 확인
            restored_bytes = self.csv_path.read_bytes()
            self.assertEqual(restored_bytes, self.original_bytes, "파일이 롤백되어야 함")

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_empty_updates(self):
        """빈 updates 처리 (no-op 테스트)."""
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            updates = {}
            result = efx.patch_csv(updates)

            self.assertTrue(result)

            # 파일 불변
            restored_bytes = self.csv_path.read_bytes()
            self.assertEqual(restored_bytes, self.original_bytes)

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_preserves_other_columns(self):
        """다른 컬럼 불변성 테스트."""
        original_csv = efx._MASTER_CSV
        efx._MASTER_CSV = self.csv_path

        try:
            # 원본 첫 행 읽기
            with self.csv_path.open(encoding="utf-8", newline="") as f:
                original_rows = list(csv.DictReader(f))
            original_row_0 = original_rows[0].copy()

            # idx=0의 m6만 갱신
            updates = {0: {"m6-valence_median": "0.99"}}
            efx.patch_csv(updates)

            # 수정 후 읽기
            with self.csv_path.open(encoding="utf-8", newline="") as f:
                new_rows = list(csv.DictReader(f))
            new_row_0 = new_rows[0]

            # m6은 변경, 나머지는 불변
            self.assertEqual(new_row_0["m6-valence_median"], "0.99")
            self.assertEqual(new_row_0["idx"], original_row_0["idx"])
            self.assertEqual(new_row_0["band"], original_row_0["band"])
            self.assertEqual(new_row_0["song"], original_row_0["song"])
            self.assertEqual(new_row_0["m9-instr_stem_ratio"], original_row_0["m9-instr_stem_ratio"])
            self.assertEqual(new_row_0["m11-speech_median"], original_row_0["m11-speech_median"])

        finally:
            efx._MASTER_CSV = original_csv

    def test_patch_handles_crlf(self):
        """CRLF 개행 방식 유지 테스트."""
        original_csv = efx._MASTER_CSV

        # CRLF 버전의 CSV 생성
        crlf_csv = Path(self.tmpdir.name) / "test_crlf.csv"
        with open(crlf_csv, "wb") as f:
            # 수동으로 CRLF 작성
            f.write(b"idx,band,song,m6-valence_median,m9-instr_stem_ratio,m11-speech_median\r\n")
            f.write(b"0,poppin_party,Song A,0.5,0.3,0.2\r\n")
            f.write(b"1,roselia,Song B,,0.4,0.25\r\n")

        efx._MASTER_CSV = crlf_csv

        try:
            updates = {1: {"m6-valence_median": "0.7"}}
            efx.patch_csv(updates)

            # 파일 읽기 및 개행 문자 확인
            modified_bytes = crlf_csv.read_bytes()
            self.assertIn(b"\r\n", modified_bytes, "CRLF가 유지되어야 함")

        finally:
            efx._MASTER_CSV = original_csv


if __name__ == "__main__":
    unittest.main()
