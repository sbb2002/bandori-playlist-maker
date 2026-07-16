"""신곡 오디오 다운로드(yt-dlp) — 형제 fetch_audio.py의 안티봇 원칙 축소판.

CI(데이터센터 IP)는 YouTube 봇월에 막히는 것이 형제 프로젝트에서 실증됐으므로
(그쪽 pipeline.yml 주석 참조), 이 모듈은 **집(레지덴셜) IP 로컬 실행** 전제다.

형제 `src/tools/cluster/fetch_audio.py`의 가이드라인(docs/idea/260703.md 5원칙)을
신곡 소량 처리에 맞게 축소 적용:
  [G1] -f ba -x (오디오만)      [G2] 곡간 30~60s 무작위 대기
  [G3] --sleep-requests 5       [G4] --limit-rate 250K
  [G5] 크롬 UA (쿠키는 기본 미사용 — 본계정 리스크 회피)
추가: --js-runtimes node (nsig 서명 해독, 403 방지), 모노 48kHz wav 유지(사용자 확정),
ffmpeg 미설치 시 imageio_ffmpeg 바이너리를 임시 폴더에 ffmpeg.exe로 복사해 연결
(perceptual_features._ffmpeg_location 관례).

출력 파일명 규약: <band>__<idx:03d>.wav (전 파이프라인 공통, 전역 idx).
음원 = 저작물 → 분석 후 폐기 대상. 기본 저장처는 형제 데브 레포의 gitignore된
audio_full 캐시(기존 추출 스크립트들이 참조하는 위치, 사용자 승인 2026-07-15).

외부 의존: yt-dlp (python -m yt_dlp), imageio_ffmpeg(ffmpeg 미설치 시).
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sources import DEFAULT_SORTER_REPO

DEFAULT_AUDIO_DIR = DEFAULT_SORTER_REPO / "src" / "content" / "cluster" / "audio_full"

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

MIN_SLEEP, MAX_SLEEP = 30.0, 60.0   # [G2]
MIN_WAV_BYTES = 1024                 # fetch_audio·orchestrate와 동일한 성공 판정


def ffmpeg_location() -> str | None:
    """ffmpeg가 PATH에 없으면 imageio_ffmpeg 바이너리를 임시 bin 폴더에
    ffmpeg.exe로 복사해 그 폴더 경로를 반환(yt-dlp --ffmpeg-location 용)."""
    if shutil.which("ffmpeg"):
        return None
    import imageio_ffmpeg
    exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    bindir = Path(tempfile.gettempdir()) / "bpm_autoloader_ffbin"
    bindir.mkdir(parents=True, exist_ok=True)
    tgt = bindir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not tgt.exists():
        shutil.copy(exe, tgt)
    return str(bindir)


def js_runtime() -> str | None:
    """yt-dlp nsig 서명 해독용 JS 런타임(deno 우선, 없으면 node)."""
    for rt in ("deno", "node"):
        if shutil.which(rt):
            return rt
    return None


def build_cmd(url: str, out_tmpl: str, *, ffmpeg_loc: str | None,
              js_rt: str | None, sample_rate: int = 48000) -> list[str]:
    """yt-dlp 명령 구성 — fetch_audio.build_cmd 축소판(쿠키 없음)."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "ba",                                  # [G1]
        "-x", "--audio-format", "wav",               # [G1]
        "--audio-quality", "0",
        "--no-playlist",
        "--sleep-requests", "5",                     # [G3]
        "--limit-rate", "250K",                      # [G4]
        "--user-agent", CHROME_UA,                   # [G5]
        "--retries", "3",
        "--fragment-retries", "3",
        "--extractor-retries", "3",
        "--postprocessor-args", f"ffmpeg:-ac 1 -ar {sample_rate}",  # 모노 48kHz 유지
        "--no-progress",
        "-o", out_tmpl,
    ]
    if js_rt:
        cmd += ["--js-runtimes", js_rt]
    if ffmpeg_loc:
        cmd += ["--ffmpeg-location", ffmpeg_loc]
    cmd.append(url)
    return cmd


def wav_path(audio_dir: Path, band: str, idx: int) -> Path:
    return audio_dir / f"{band}__{idx:03d}.wav"


def download_one(cand: dict, audio_dir: Path = DEFAULT_AUDIO_DIR) -> Path | None:
    """후보 1곡 다운로드. 성공 시 wav 경로, 실패 시 None(fail-soft).

    이미 유효한 wav(>1KB)가 있으면 재다운로드하지 않는다(재개 가능/멱등).
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = wav_path(audio_dir, cand["band"], cand["idx"])
    if out.exists() and out.stat().st_size > MIN_WAV_BYTES:
        print(f"  [cache] {out.name} 이미 존재 — 다운로드 생략", flush=True)
        return out

    cmd = build_cmd(cand["url"], str(out.with_suffix("")) + ".%(ext)s",
                    ffmpeg_loc=ffmpeg_location(), js_rt=js_runtime())
    print(f"  [dl] {out.stem} ← {cand['url']}", flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
        print(f"  ✗ yt-dlp 실패(rc={p.returncode}): {' / '.join(tail)}", flush=True)
    if out.exists() and out.stat().st_size > MIN_WAV_BYTES:
        return out
    out.unlink(missing_ok=True)      # 0바이트 찌꺼기 제거
    return None


def download_all(cands: list[dict], audio_dir: Path = DEFAULT_AUDIO_DIR) -> dict[int, Path]:
    """후보 전체를 순차 다운로드(곡간 30~60s 대기). idx→wav 경로 dict 반환."""
    got: dict[int, Path] = {}
    fresh = 0
    for i, c in enumerate(cands):
        cached = wav_path(audio_dir, c["band"], c["idx"])
        was_cached = cached.exists() and cached.stat().st_size > MIN_WAV_BYTES
        if i > 0 and fresh > 0 and not was_cached:
            pause = random.uniform(MIN_SLEEP, MAX_SLEEP)   # [G2]
            print(f"  … 곡간 대기 {pause:.0f}s", flush=True)
            time.sleep(pause)
        p = download_one(c, audio_dir)
        if p is not None:
            got[c["idx"]] = p
            if not was_cached:
                fresh += 1
    return got
