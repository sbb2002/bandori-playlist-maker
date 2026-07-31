#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_speechiness_vad.py — inaSpeechSegmenter 기반 VAD로 speech ratio 추출.

의존성: inaSpeechSegmenter (pip 설치 가능, torch/keras 기반)
출력: out/speechiness_raw.csv에 vad_speech_ratio 컬럼 추가

실행:
  python src/extract_speechiness_vad.py [--workers 2] [--limit 10]

주의: 설치 실패 시 error="vad_unavailable"로 기록하고 계속 진행.
"""

import sys
import os
import csv
import argparse
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from time import time

import numpy as np
import pandas as pd
import librosa

# ============================================================================
# INASPEECHSEGMENTER IMPORT HANDLING
# ============================================================================

try:
    from inaSpeechSegmenter import Segmenter
    INASPEECH_AVAILABLE = True
    INASPEECH_ERROR = None
except ImportError as e:
    INASPEECH_AVAILABLE = False
    INASPEECH_ERROR = str(e)

# ============================================================================
# LOGGER & ENCODING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============================================================================
# PATHS (CONVENTIONS.md)
# ============================================================================

_THIS_DIR = Path(__file__).resolve().parent          # method-11-speechiness/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-11-speechiness/
_TOPIC_DIR = _METHOD_DIR.parent                       # 20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                    # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                  # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"

VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT / "bandori-playlist-maker" / "topic" / "mfcc_analysis" / "stems" / "htdemucs"
)
# 폴더명: f"{band}__{idx:03d}/"  하위에 vocals.wav, no_vocals.wav
# ⚠️ 661곡 중 30곡분만 존재

OUT_DIR = _METHOD_DIR / "out"
SPEECHINESS_CSV = OUT_DIR / "speechiness_raw.csv"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def stem_paths(band: str, idx: int) -> tuple | None:
    """
    보컬 스템 폴더가 존재하면 (vocal_path, no_vocal_path) 반환.
    없으면 None.
    """
    stem_folder = VOCAL_STEM_DIR / f"{band}__{idx:03d}"
    vocal_path = stem_folder / "vocals.wav"
    no_vocal_path = stem_folder / "no_vocals.wav"

    if not vocal_path.exists() or not no_vocal_path.exists():
        return None

    return (vocal_path, no_vocal_path)


def extract_vad_ratio(vocal_path: Path) -> dict:
    """
    inaSpeechSegmenter를 사용하여 speech ratio 추출.

    Args:
        vocal_path: 보컬 스템 파일 경로.

    Returns:
        dict with keys:
            - vad_speech_ratio: float (0~1, speech로 라벨된 프레임 비율)
            - n_frames: int (전체 세그먼트 수)
            - duration_sec: float
            - error: None (성공 시)
    """

    if not INASPEECH_AVAILABLE:
        return {
            "vad_speech_ratio": None,
            "n_frames": None,
            "duration_sec": None,
            "error": "vad_unavailable"
        }

    try:
        # 오디오 로드
        y, sr = librosa.load(str(vocal_path), sr=16000, mono=True)
        duration_sec = len(y) / sr

        logger.debug(f"Loaded audio for VAD from {vocal_path}: {len(y)} samples @ {sr}Hz")

        # inaSpeechSegmenter 실행
        segmenter = Segmenter()
        segments = segmenter(str(vocal_path))  # [(label, start, end), ...]

        logger.debug(f"Segmenter returned {len(segments)} segments")

        if not segments:
            return {
                "vad_speech_ratio": 0.0,
                "n_frames": 0,
                "duration_sec": duration_sec,
                "error": None
            }

        # speech로 라벨된 구간 총 길이
        speech_duration = 0.0
        for label, start, end in segments:
            if "speech" in str(label).lower():
                speech_duration += (end - start)

        # 비율 계산
        vad_speech_ratio = speech_duration / duration_sec if duration_sec > 0 else 0.0
        vad_speech_ratio = np.clip(float(vad_speech_ratio), 0.0, 1.0)

        return {
            "vad_speech_ratio": vad_speech_ratio,
            "n_frames": len(segments),
            "duration_sec": duration_sec,
            "error": None
        }

    except Exception as e:
        logger.warning(f"Error in VAD extraction from {vocal_path}: {e}")
        return {
            "vad_speech_ratio": None,
            "n_frames": None,
            "duration_sec": None,
            "error": f"VAD error: {e}"
        }

# ============================================================================
# WORKER (multiprocessing)
# ============================================================================

def _worker(task: dict) -> dict:
    """
    개별 곡 처리 워커 (VAD).

    Args:
        task: dict with keys:
            - idx: int (곡 번호)
            - band: str
            - song: str
            - vocal_path: Path (또는 None if no stem)

    Returns:
        dict with keys:
            - idx, band, song
            - vad_speech_ratio
            - n_frames
            - error
    """

    idx = task["idx"]
    band = task["band"]
    song = task["song"]
    vocal_path = task["vocal_path"]

    try:
        # 스템이 없으면
        if vocal_path is None:
            return {
                "idx": idx,
                "band": band,
                "song": song,
                "vad_speech_ratio": None,
                "n_frames": None,
                "error": "no_stem"
            }

        if not vocal_path.exists():
            return {
                "idx": idx,
                "band": band,
                "song": song,
                "vad_speech_ratio": None,
                "n_frames": None,
                "error": f"Audio file not found: {vocal_path}"
            }

        result = extract_vad_ratio(vocal_path)

        return {
            "idx": idx,
            "band": band,
            "song": song,
            "vad_speech_ratio": result["vad_speech_ratio"],
            "n_frames": result["n_frames"],
            "error": result["error"]
        }

    except Exception as e:
        logger.error(f"Worker crashed on idx={idx}: {e}")
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "vad_speech_ratio": None,
            "n_frames": None,
            "error": f"Worker error: {e}"
        }

# ============================================================================
# RESUME SUPPORT
# ============================================================================

def get_done_idxs(csv_path: Path) -> set:
    """이미 vad_speech_ratio가 기록된 idx 읽기."""
    if not csv_path.exists():
        return set()

    done_idxs = set()
    try:
        df = pd.read_csv(csv_path, usecols=["idx", "vad_speech_ratio"])
        # vad_speech_ratio가 NaN이 아닌 행만 완료된 것으로 취급
        done_idxs = set(df[df["vad_speech_ratio"].notna()]["idx"].unique())
    except Exception as e:
        logger.warning(f"Failed to read done_idxs from {csv_path}: {e}")

    return done_idxs

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract VAD (speech ratio) features using inaSpeechSegmenter."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of worker processes (default 2, reduced for model loading cost)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N songs (for testing)"
    )
    parser.add_argument(
        "--idx",
        type=str,
        default=None,
        help="Process only specific idx (comma-separated, e.g. 0,1,2)"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore existing VAD output and restart from scratch"
    )

    args = parser.parse_args()

    # ========================================================================
    # SETUP
    # ========================================================================

    logger.info(f"Starting VAD extraction (method-11-speechiness)")
    logger.info(f"inaSpeechSegmenter available: {INASPEECH_AVAILABLE}")
    if INASPEECH_ERROR:
        logger.warning(f"inaSpeechSegmenter import error: {INASPEECH_ERROR}")
    logger.info(f"Workers: {args.workers}, Limit: {args.limit}, Fresh: {args.fresh}")

    # 출력 디렉터리 생성 (speechiness_raw.csv는 이미 있어야 함)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # LOAD SONGS_MASTER
    # ========================================================================

    logger.info(f"Loading songs_master.csv: {MASTER_CSV}")
    try:
        df_master = pd.read_csv(MASTER_CSV)
    except Exception as e:
        logger.error(f"Failed to load songs_master.csv: {e}")
        sys.exit(1)

    logger.info(f"Loaded {len(df_master)} songs from songs_master.csv")

    # ========================================================================
    # FILTER TASKS (VAD가 아직 계산되지 않은 것만)
    # ========================================================================

    done_idxs = set()
    if SPEECHINESS_CSV.exists() and not args.fresh:
        done_idxs = get_done_idxs(SPEECHINESS_CSV)
        logger.info(f"Resume: found {len(done_idxs)} songs with VAD already processed")

    # 처리할 idx 결정
    if args.idx:
        # 특정 idx만
        selected_idxs = set(int(x.strip()) for x in args.idx.split(","))
        tasks_df = df_master[df_master["idx"].isin(selected_idxs)].copy()
        logger.info(f"Filtered to {len(tasks_df)} songs by --idx")
    else:
        tasks_df = df_master.copy()

    if not args.fresh:
        # Resume: 이미 처리된 것 제외
        tasks_df = tasks_df[~tasks_df["idx"].isin(done_idxs)].copy()

    if args.limit:
        tasks_df = tasks_df.head(args.limit)
        logger.info(f"Limited to first {args.limit} songs")

    logger.info(f"Processing {len(tasks_df)} songs for VAD")

    # ========================================================================
    # BUILD TASKS
    # ========================================================================

    tasks = []
    for _, row in tasks_df.iterrows():
        idx = int(row["idx"])
        band = row["band"]
        song = row["song"]

        # 보컬 스템 경로 확인
        paths = stem_paths(band, idx)
        vocal_path = paths[0] if paths else None

        tasks.append({
            "idx": idx,
            "band": band,
            "song": song,
            "vocal_path": vocal_path
        })

    # ========================================================================
    # PROCESS (multiprocessing)
    # ========================================================================

    if not INASPEECH_AVAILABLE:
        logger.warning(
            f"inaSpeechSegmenter not available. All songs will be marked with error='vad_unavailable'."
        )

    logger.info(f"Starting multiprocessing with {args.workers} workers...")
    start_time = time()

    results = []
    with Pool(processes=args.workers) as pool:
        for i, result in enumerate(pool.imap_unordered(_worker, tasks, chunksize=1)):
            results.append(result)

            # 진행 로그 (10곡마다)
            if (i + 1) % 10 == 0:
                elapsed = time() - start_time
                rate = (i + 1) / (elapsed + 1e-6)
                eta_sec = (len(tasks) - i - 1) / (rate + 1e-6)

                n_ok = sum(1 for r in results if r["error"] is None)
                n_err = len(results) - n_ok

                logger.info(
                    f"Progress {i + 1}/{len(tasks)} | "
                    f"ok={n_ok} err={n_err} | "
                    f"rate={rate:.1f} songs/sec | "
                    f"ETA {eta_sec/60:.1f}m"
                )

    # ========================================================================
    # UPDATE RESULTS IN SPEECHINESS_RAW.CSV
    # ========================================================================

    if not SPEECHINESS_CSV.exists():
        logger.warning(
            f"speechiness_raw.csv not found at {SPEECHINESS_CSV}. "
            f"Please run extract_speechiness_stem.py first."
        )
        logger.info("Saving VAD results to temporary table (not merging)...")
        # 그냥 결과 로깅만 함
        return

    logger.info(f"Updating {SPEECHINESS_CSV} with VAD results...")

    # 기존 CSV 읽기
    try:
        df_existing = pd.read_csv(SPEECHINESS_CSV)
    except Exception as e:
        logger.error(f"Failed to read existing CSV: {e}")
        sys.exit(1)

    # VAD 결과를 딕셔너리로 구성
    vad_dict = {}
    for result in results:
        idx = result["idx"]
        vad_dict[idx] = {
            "vad_speech_ratio": result["vad_speech_ratio"],
            "vad_n_frames": result["n_frames"],
            "vad_error": result["error"]
        }

    # vad_speech_ratio 컬럼 추가 (기본값 NaN)
    if "vad_speech_ratio" not in df_existing.columns:
        df_existing["vad_speech_ratio"] = np.nan
    if "vad_n_frames" not in df_existing.columns:
        df_existing["vad_n_frames"] = None
    if "vad_error" not in df_existing.columns:
        df_existing["vad_error"] = None

    # VAD 결과 병합
    for idx, vad_values in vad_dict.items():
        if idx in df_existing["idx"].values:
            row_idx = df_existing[df_existing["idx"] == idx].index[0]
            df_existing.loc[row_idx, "vad_speech_ratio"] = vad_values["vad_speech_ratio"]
            df_existing.loc[row_idx, "vad_n_frames"] = vad_values["vad_n_frames"]
            # vad_error는 원래 error와 별도로 기록하거나, 기존 error가 있으면 유지
            if df_existing.loc[row_idx, "error"] is None or pd.isna(df_existing.loc[row_idx, "error"]):
                df_existing.loc[row_idx, "error"] = vad_values["vad_error"]

    # CSV 저장
    try:
        df_existing.to_csv(SPEECHINESS_CSV, index=False, encoding="utf-8")
        logger.info(f"Updated {SPEECHINESS_CSV} with VAD results")
    except Exception as e:
        logger.error(f"Failed to save updated CSV: {e}")
        sys.exit(1)

    # ========================================================================
    # SUMMARY
    # ========================================================================

    n_ok = sum(1 for r in results if r["error"] is None)
    n_err = len(results) - n_ok
    elapsed = time() - start_time

    logger.info(
        f"\n{'='*60}\n"
        f"VAD EXTRACTION DONE\n"
        f"  Total: {len(results)} songs\n"
        f"  Success: {n_ok}\n"
        f"  Error: {n_err}\n"
        f"  Elapsed: {elapsed/60:.1f}m\n"
        f"  Output: {SPEECHINESS_CSV}\n"
        f"{'='*60}"
    )

if __name__ == "__main__":
    main()
