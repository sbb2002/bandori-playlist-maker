"""camelot.py 단위 테스트 + song_features_with_proxies.csv 통합 검증.

실행: python scripts/data/test_camelot.py
       (또는) python -m unittest scripts.data.test_camelot -v

표준 라이브러리만 사용한다 (unittest, csv, os, re).
"""

from __future__ import annotations

import csv
import os
import unittest

from camelot import (
    CAMELOT_TO_KEY,
    KEY_TO_CAMELOT,
    adjacent,
    is_adjacent,
    to_camelot,
)

# 데이터팀 팀장 명세(§⑤) 상 읽기 전용 검증 대상 CSV 경로.
_CSV_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "bandori-song-sorter", "side-project", "genre-features",
        "song_features_with_proxies.csv",
    )
)

_ALL_NUMBERS = [str(n) for n in range(1, 13)]
_ALL_LETTERS = ("A", "B")


class ToCamelotTests(unittest.TestCase):
    def test_24_keys_mapped(self) -> None:
        """key 24종 전수가 매핑 테이블에 존재해야 한다."""
        self.assertEqual(len(KEY_TO_CAMELOT), 24)

    def test_24_camelot_codes_no_duplicates(self) -> None:
        """24개 key가 24개의 서로 다른 Camelot 코드로 1:1 매핑되어야 한다(중복 없음)."""
        codes = list(KEY_TO_CAMELOT.values())
        self.assertEqual(len(codes), 24)
        self.assertEqual(len(set(codes)), 24, "Camelot 코드 중복 발생")

    def test_all_12_numbers_and_both_letters_covered(self) -> None:
        """1~12 각 번호에 A, B가 정확히 하나씩 존재해야 한다(전체 휠 커버)."""
        expected = {f"{n}{letter}" for n in _ALL_NUMBERS for letter in _ALL_LETTERS}
        self.assertEqual(set(KEY_TO_CAMELOT.values()), expected)

    def test_reverse_mapping_is_bijective(self) -> None:
        """CAMELOT_TO_KEY가 KEY_TO_CAMELOT의 완전한 역함수여야 한다."""
        self.assertEqual(len(CAMELOT_TO_KEY), 24)
        for key, code in KEY_TO_CAMELOT.items():
            self.assertEqual(CAMELOT_TO_KEY[code], key)

    def test_known_examples(self) -> None:
        """데이터팀 팀장 티켓3 명세(§⑤)에 명시된 대표 매핑 값 검증."""
        examples = {
            "Bmaj": "1B",
            "F#maj": "2B",
            "Amaj": "11B",
            "Emin": "9A",
            "Amin": "8A",
            "G#min": "1A",
            "D#min": "2A",
        }
        for key, expected_code in examples.items():
            with self.subTest(key=key):
                self.assertEqual(to_camelot(key), expected_code)

    def test_major_is_b_minor_is_a(self) -> None:
        """뮤직 이론상 A=minor, B=major 규칙이 전 항목에서 일관되어야 한다."""
        for key, code in KEY_TO_CAMELOT.items():
            with self.subTest(key=key):
                if key.endswith("maj"):
                    self.assertTrue(code.endswith("B"))
                else:
                    self.assertTrue(code.endswith("A"))

    def test_unknown_key_raises_value_error(self) -> None:
        for bad_key in ["Absmaj", "Hmaj", "Amajor", "amaj", "A#Maj", "", "A#flat", "Bbmin"]:
            with self.subTest(bad_key=bad_key):
                with self.assertRaises(ValueError):
                    to_camelot(bad_key)


class AdjacentTests(unittest.TestCase):
    def test_relative_major_minor(self) -> None:
        """같은 번호의 A<->B 전환이 인접 집합에 포함되어야 한다."""
        self.assertIn("8B", adjacent("8A"))
        self.assertIn("8A", adjacent("8B"))

    def test_example_8a(self) -> None:
        self.assertEqual(adjacent("8A"), {"8B", "7A", "9A"})

    def test_neighbor_numbers_same_letter(self) -> None:
        self.assertEqual(adjacent("5B"), {"5A", "4B", "6B"})

    def test_wraparound_12_to_1(self) -> None:
        """12<->1 순환 인접이 성립해야 한다."""
        self.assertEqual(adjacent("12A"), {"12B", "11A", "1A"})
        self.assertEqual(adjacent("1A"), {"1B", "12A", "2A"})
        self.assertEqual(adjacent("12B"), {"12A", "11B", "1B"})
        self.assertEqual(adjacent("1B"), {"1A", "12B", "2B"})

    def test_adjacent_set_size_always_three(self) -> None:
        for n in _ALL_NUMBERS:
            for letter in _ALL_LETTERS:
                with self.subTest(code=f"{n}{letter}"):
                    self.assertEqual(len(adjacent(f"{n}{letter}")), 3)

    def test_self_not_in_own_adjacent_set(self) -> None:
        for n in _ALL_NUMBERS:
            for letter in _ALL_LETTERS:
                code = f"{n}{letter}"
                with self.subTest(code=code):
                    self.assertNotIn(code, adjacent(code))

    def test_adjacency_is_symmetric(self) -> None:
        """a가 b의 인접이면 b도 a의 인접이어야 한다(무방향 그래프)."""
        for n in _ALL_NUMBERS:
            for letter in _ALL_LETTERS:
                a = f"{n}{letter}"
                for b in adjacent(a):
                    with self.subTest(a=a, b=b):
                        self.assertIn(a, adjacent(b))

    def test_invalid_camelot_raises(self) -> None:
        for bad_code in ["0A", "13A", "8C", "A8", "8", "", "8a"]:
            with self.subTest(bad_code=bad_code):
                with self.assertRaises(ValueError):
                    adjacent(bad_code)


class IsAdjacentTests(unittest.TestCase):
    def test_matches_adjacent_set(self) -> None:
        self.assertTrue(is_adjacent("8A", "8B"))
        self.assertTrue(is_adjacent("8A", "7A"))
        self.assertTrue(is_adjacent("8A", "9A"))
        self.assertFalse(is_adjacent("8A", "10A"))

    def test_self_is_not_adjacent(self) -> None:
        """동일 코드는 인접으로 취급하지 않는다(adjacent()가 자기 자신을 제외하는 것과 일관)."""
        self.assertFalse(is_adjacent("8A", "8A"))

    def test_wraparound(self) -> None:
        self.assertTrue(is_adjacent("12A", "1A"))
        self.assertTrue(is_adjacent("1A", "12A"))

    def test_invalid_codes_raise(self) -> None:
        with self.assertRaises(ValueError):
            is_adjacent("13A", "1A")
        with self.assertRaises(ValueError):
            is_adjacent("1A", "13A")


class CsvIntegrationTests(unittest.TestCase):
    """song_features_with_proxies.csv (읽기 전용) key 컬럼 660행 통합 검증."""

    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isfile(_CSV_PATH):
            raise unittest.SkipTest(f"CSV 파일을 찾을 수 없음: {_CSV_PATH}")
        with open(_CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cls.rows = list(reader)

    def test_row_count_is_660(self) -> None:
        self.assertEqual(len(self.rows), 660)

    def test_all_rows_map_successfully(self) -> None:
        """660행 전부 to_camelot 성공(누락 0)을 실제 실행으로 확인한다."""
        failures: list[tuple[int, str, str]] = []
        for row in self.rows:
            key = row["key"]
            try:
                to_camelot(key)
            except ValueError as exc:
                failures.append((int(row["idx"]), key, str(exc)))

        total = len(self.rows)
        success = total - len(failures)
        print(
            f"\n[CSV 통합 검증] 총 {total}행 / 매핑 성공 {success}행 / "
            f"실패 {len(failures)}행 (실패 목록: {failures[:5]}{'...' if len(failures) > 5 else ''})"
        )
        self.assertEqual(failures, [], f"매핑 실패 {len(failures)}건 발생: {failures}")

    def test_observed_key_values_subset_of_mapping_table(self) -> None:
        """CSV에서 관측된 key 고유값이 정확히 24종이며 전부 매핑 테이블에 존재해야 한다."""
        observed = {row["key"] for row in self.rows}
        print(f"[CSV 통합 검증] 관측된 key 고유값 수: {len(observed)}")
        self.assertEqual(len(observed), 24)
        self.assertTrue(observed.issubset(KEY_TO_CAMELOT.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
