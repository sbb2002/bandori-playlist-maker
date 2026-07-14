"""fetch_new.py 단위 테스트 — 명령 구성(안티봇 원칙)·파일명 규약(네트워크 없음)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_new  # noqa: E402


class BuildCmdTest(unittest.TestCase):
    def test_antibot_flags_present(self):
        cmd = fetch_new.build_cmd("https://youtu.be/x", "out.%(ext)s",
                                  ffmpeg_loc="C:/ffbin", js_rt="node")
        joined = " ".join(cmd)
        self.assertIn("-f ba", joined)                         # [G1] 오디오만
        self.assertIn("-x --audio-format wav", joined)         # [G1]
        self.assertIn("--sleep-requests 5", joined)            # [G3]
        self.assertIn("--limit-rate 250K", joined)             # [G4]
        self.assertIn("--user-agent", joined)                  # [G5]
        self.assertIn("ffmpeg:-ac 1 -ar 48000", joined)        # 모노 48kHz 유지
        self.assertIn("--js-runtimes node", joined)            # nsig 서명
        self.assertIn("--ffmpeg-location C:/ffbin", joined)
        self.assertNotIn("--cookies-from-browser", joined)     # 본계정 리스크 회피
        self.assertEqual(cmd[-1], "https://youtu.be/x")

    def test_optional_parts_omitted(self):
        cmd = fetch_new.build_cmd("u", "o", ffmpeg_loc=None, js_rt=None)
        joined = " ".join(cmd)
        self.assertNotIn("--js-runtimes", joined)
        self.assertNotIn("--ffmpeg-location", joined)


class WavPathTest(unittest.TestCase):
    def test_naming_convention(self):
        p = fetch_new.wav_path(Path("cache"), "mygo", 660)
        self.assertEqual(p.name, "mygo__660.wav")

    def test_zero_padding(self):
        p = fetch_new.wav_path(Path("cache"), "afterglow", 7)
        self.assertEqual(p.name, "afterglow__007.wav")


if __name__ == "__main__":
    unittest.main()
