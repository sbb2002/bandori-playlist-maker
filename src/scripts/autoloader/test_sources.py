"""sources.py 단위 테스트 — 신곡 감별(video_id 기준·중복 업로드 제외·멱등)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources  # noqa: E402


def _sorter_row(idx: int, band: str, song: str, vid: str) -> dict:
    return {"idx": str(idx), "band": band, "song": song,
            "url": f"https://youtu.be/{vid}"}


def _master_row(idx: int, band: str, vid: str) -> dict:
    return {"idx": str(idx), "band": band, "song": f"s{idx}", "video_id": vid}


class DetectNewTest(unittest.TestCase):
    def test_new_songs_only(self):
        vid_a, vid_b, vid_new = "AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"
        sorter = [
            _sorter_row(0, "mygo", "old", vid_a),
            _sorter_row(660, "mygo", "신곡", vid_new),
        ]
        master = [_master_row(0, "mygo", vid_a), _master_row(1, "roselia", vid_b)]
        got = sources.detect_new(sorter, master)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["idx"], 660)
        self.assertEqual(got[0]["video_id"], vid_new)
        self.assertEqual(got[0]["url"], f"https://youtu.be/{vid_new}")

    def test_dropped_duplicate_uploads_excluded(self):
        # master에서 의도적으로 제거된 중복 업로드 idx는 후보로 재등장하면 안 된다.
        drop_idx = next(iter(sources.DROPPED_DUPLICATE_IDXS))
        sorter = [_sorter_row(drop_idx, "roselia", "dup", "DDDDDDDDDDD")]
        got = sources.detect_new(sorter, [])
        self.assertEqual(got, [])

    def test_idempotent_when_all_known(self):
        vid = "EEEEEEEEEEE"
        sorter = [_sorter_row(660, "mygo", "신곡", vid)]
        master = [_master_row(660, "mygo", vid)]
        self.assertEqual(sources.detect_new(sorter, master), [])

    def test_sorted_by_idx(self):
        sorter = [
            _sorter_row(662, "mygo", "c", "CCCCCCCCCC2"),
            _sorter_row(660, "mygo", "a", "AAAAAAAAAA2"),
            _sorter_row(661, "mygo", "b", "BBBBBBBBBB2"),
        ]
        got = sources.detect_new(sorter, [])
        self.assertEqual([c["idx"] for c in got], [660, 661, 662])


class AudioMapTest(unittest.TestCase):
    def test_entries_by_idx_positional(self):
        amap = {"songs": [{"band": "x", "song": "s0"}, {"band": "y", "song": "s1"}]}
        got = sources.audio_map_entries_by_idx(amap)
        self.assertEqual(got[0]["song"], "s0")
        self.assertEqual(got[1]["band"], "y")


if __name__ == "__main__":
    unittest.main()
