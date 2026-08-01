#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_speechiness_stem.py — Scheirer-Slaney 4Hz 변조 에너지로 speechiness 추출.

의존성: librosa, numpy, scipy (네이티브 - Windows Python 가능)
출력: out/speechiness_raw.csv + out/timeseries/<idx>_modulation.npy

실행:
  python src/extract_speechiness_stem.py [--workers 4] [--limit 10]
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
from scipy import signal
from scipy.signal import windows

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
TIMESERIES_DIR = OUT_DIR / "timeseries"
SPEECHINESS_CSV = OUT_DIR / "csv" / "speechiness_raw.csv"

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


def modulation_energy_ratio(y: np.ndarray, sr: int, frame_sec: float = 1.0,
                             hop_percent: float = 0.5) -> np.ndarray:
    """
    Scheirer-Slaney 4Hz 변조 에너지 비 계산.

    1) 신호의 envelope 추출: 정류 → 저역통과
    2) 프레임(frame_sec 단위, hop_percent 겹침)마다 envelope의 스펙트럼 계산
    3) 3-4Hz 대역 에너지 / 전체 변조 스펙트럼 에너지 = 해당 프레임의 비율

    Args:
        y: 오디오 신호 (1D ndarray)
        sr: 샘플링 레이트 (Hz)
        frame_sec: 프레임 길이 (초, 기본 1.0)
        hop_percent: 프레임 겹침 비율 (0.5 = 50%, 기본)

    Returns:
        프레임별 변조 에너지 비 시계열 (1D ndarray, 값은 0~1)
    """

    # 1) Envelope 추출: 정류(rectify) → 저역통과
    # 절댓값으로 정류
    y_rectified = np.abs(y)

    # 저역통과 필터 (20Hz cutoff)
    # Butterworth 2차 필터
    nyquist = sr / 2.0
    low_cutoff = 20.0 / nyquist  # 정규화
    b, a = signal.butter(2, low_cutoff, btype='low')

    # 양쪽 끝에서의 edge 효과 제거를 위해 filtfilt 사용
    try:
        y_envelope = signal.filtfilt(b, a, y_rectified)
    except Exception as e:
        logger.warning(f"filtfilt failed: {e}, using lfilter instead")
        y_envelope = signal.lfilter(b, a, y_rectified)

    # 2) 프레임 분할
    frame_samples = int(frame_sec * sr)
    hop_samples = int(frame_samples * (1 - hop_percent))  # 50% 겹침 = 50% 이동

    n_frames = (len(y_envelope) - frame_samples) // hop_samples + 1

    if n_frames <= 0:
        # 신호가 너무 짧으면 전체 신호 대상으로 한 프레임만 생성
        n_frames = 1
        hop_samples = len(y_envelope) - frame_samples + 1 if frame_samples > len(y_envelope) else 1
        frame_samples = len(y_envelope)

    ratios = []

    for frame_idx in range(n_frames):
        start = frame_idx * hop_samples
        end = start + frame_samples

        # 경계 검사
        if end > len(y_envelope):
            end = len(y_envelope)
            if end - start < frame_samples // 2:  # 프레임이 너무 작으면 스킵
                break

        frame_envelope = y_envelope[start:end]

        # FFT로 스펙트럼 계산
        # 윈도우 적용 (Hann)
        window = windows.hann(len(frame_envelope))
        frame_windowed = frame_envelope * window

        # FFT
        spec = np.fft.rfft(frame_windowed)
        freqs = np.fft.rfftfreq(len(frame_windowed), d=1.0/sr)

        # 전력 스펙트럼
        power = np.abs(spec) ** 2

        # 3-4Hz 대역 에너지와 전체 변조 스펙트럼(0.5-20Hz) 에너지 계산
        # 3-4Hz 대역
        band_3_4_mask = (freqs >= 3.0) & (freqs <= 4.0)
        energy_3_4 = np.sum(power[band_3_4_mask])

        # 전체 변조 스펙트럼 (0.5-20Hz)
        modulation_mask = (freqs >= 0.5) & (freqs <= 20.0)
        energy_modulation = np.sum(power[modulation_mask])

        # 비율 계산
        if energy_modulation > 0:
            ratio = energy_3_4 / energy_modulation
        else:
            ratio = 0.0

        # 비율을 0~1로 clamp
        ratio = np.clip(float(ratio), 0.0, 1.0)
        ratios.append(ratio)

    return np.array(ratios, dtype=np.float32)


def extract_features(vocal_path: Path) -> dict:
    """
    단일 곡(보컬 스템)에서 변조 에너지 비 시계열 + 요약통계 추출.

    Args:
        vocal_path: 보컬 스템 파일 경로.

    Returns:
        dict with keys:
            - modulation_series: 1D ndarray (프레임별 원시값)
            - speech_median: float
            - speech_p10: float
            - speech_p90: float
            - speech_std: float
            - n_frames: int (시계열 길이)
            - duration_sec: float
            - error: None (성공 시)
    """

    try:
        # librosa로 오디오 로드 (22050Hz, 모노)
        y, sr = librosa.load(str(vocal_path), sr=22050, mono=True)

        logger.debug(f"Loaded audio from {vocal_path}: {len(y)} samples @ {sr}Hz")

        # 변조 에너지 비 계산
        modulation_series = modulation_energy_ratio(y, sr)

        n_frames = len(modulation_series)
        duration_sec = len(y) / sr

        # 요약통계
        speech_median = float(np.median(modulation_series))
        speech_p10 = float(np.percentile(modulation_series, 10))
        speech_p90 = float(np.percentile(modulation_series, 90))
        speech_std = float(np.std(modulation_series))

        return {
            "modulation_series": modulation_series,
            "speech_median": speech_median,
            "speech_p10": speech_p10,
            "speech_p90": speech_p90,
            "speech_std": speech_std,
            "n_frames": n_frames,
            "duration_sec": duration_sec,
            "error": None
        }

    except Exception as e:
        logger.warning(f"Error extracting features from {vocal_path}: {e}")
        return {
            "modulation_series": None,
            "speech_median": None,
            "speech_p10": None,
            "speech_p90": None,
            "speech_std": None,
            "n_frames": None,
            "duration_sec": None,
            "error": str(e)
        }

# ============================================================================
# WORKER (multiprocessing)
# ============================================================================

def _worker(task: dict) -> dict:
    """
    개별 곡 처리 워커.

    Args:
        task: dict with keys:
            - idx: int (곡 번호)
            - band: str
            - song: str
            - vocal_path: Path (또는 None if no stem)

    Returns:
        dict with keys:
            - idx, band, song, duration_sec
            - speech_median, speech_p10, speech_p90, speech_std
            - n_frames
            - modulation_series (timeseries npy 저장용)
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
                "duration_sec": None,
                "speech_median": None,
                "speech_p10": None,
                "speech_p90": None,
                "speech_std": None,
                "n_frames": None,
                "modulation_series": None,
                "error": "no_stem"
            }

        if not vocal_path.exists():
            return {
                "idx": idx,
                "band": band,
                "song": song,
                "duration_sec": None,
                "speech_median": None,
                "speech_p10": None,
                "speech_p90": None,
                "speech_std": None,
                "n_frames": None,
                "modulation_series": None,
                "error": f"Audio file not found: {vocal_path}"
            }

        result = extract_features(vocal_path)

        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": result["duration_sec"],
            "speech_median": result["speech_median"],
            "speech_p10": result["speech_p10"],
            "speech_p90": result["speech_p90"],
            "speech_std": result["speech_std"],
            "n_frames": result["n_frames"],
            "modulation_series": result["modulation_series"],
            "error": result["error"]
        }

    except Exception as e:
        logger.error(f"Worker crashed on idx={idx}: {e}")
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": None,
            "speech_median": None,
            "speech_p10": None,
            "speech_p90": None,
            "speech_std": None,
            "n_frames": None,
            "modulation_series": None,
            "error": f"Worker error: {e}"
        }

# ============================================================================
# RESUME SUPPORT
# ============================================================================

def get_done_idxs(csv_path: Path) -> set:
    """이미 처리된 idx 읽기. error가 None/NaN인 행은 미처리로 간주."""
    if not csv_path.exists():
        return set()

    done_idxs = set()
    try:
        df = pd.read_csv(csv_path, usecols=["idx", "error"])
        # error가 None/NaN인 행은 제외 (미처리)
        done_idxs = set(df[df["error"].notna()]["idx"].unique())
    except Exception as e:
        logger.warning(f"Failed to read done_idxs from {csv_path}: {e}")

    return done_idxs

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract speechiness features using Scheirer-Slaney 4Hz modulation energy."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker processes (default 4)"
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
        help="Ignore existing output and restart from scratch"
    )

    args = parser.parse_args()

    # ========================================================================
    # SETUP
    # ========================================================================

    logger.info(f"Starting speechiness extraction (method-11-speechiness)")
    logger.info(f"Workers: {args.workers}, Limit: {args.limit}, Fresh: {args.fresh}")

    # 출력 디렉터리 생성
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)

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
    # FILTER TASKS
    # ========================================================================

    done_idxs = set()
    if SPEECHINESS_CSV.exists() and not args.fresh:
        done_idxs = get_done_idxs(SPEECHINESS_CSV)
        logger.info(f"Resume: found {len(done_idxs)} already processed songs")

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

    logger.info(f"Processing {len(tasks_df)} songs")

    # ========================================================================
    # BUILD TASKS
    # ========================================================================

    tasks = []
    for _, row in tasks_df.iterrows():
        idx = int(row["idx"])
        band = row["band"]
        song = row["song"]
        file_idx = int(row.get("file_idx", idx))  # 오디오 파일명 번호(2026-08-01: idx와 분리)

        # 보컬 스템 경로 확인
        paths = stem_paths(band, file_idx)
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
    # SAVE RESULTS
    # ========================================================================

    logger.info(f"Saving results to {SPEECHINESS_CSV}...")

    # CSV 레이아웃
    csv_fieldnames = [
        "idx", "band", "song", "duration_sec",
        "speech_median", "speech_p10", "speech_p90", "speech_std",
        "n_frames",
        "error",
        "vad_speech_ratio", "vad_n_frames", "vad_error"  # VAD 컬럼 (있으면 유지)
    ]

    # 기존 CSV 읽기 (resume 시)
    existing_rows = {}
    if SPEECHINESS_CSV.exists() and not args.fresh:
        try:
            with open(SPEECHINESS_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    idx = int(row["idx"])
                    # 기존 VAD 컬럼이 있으면 유지
                    existing_rows[idx] = row
        except Exception as e:
            logger.warning(f"Failed to read existing CSV: {e}")

    # 새 결과 추가
    for result in results:
        idx = result["idx"]
        # timeseries 저장 (성공 시)
        if result["modulation_series"] is not None:
            npy_path = TIMESERIES_DIR / f"{idx:03d}_modulation.npy"
            try:
                np.save(str(npy_path), result["modulation_series"])
                logger.debug(f"Saved timeseries: {npy_path}")
            except Exception as e:
                logger.warning(f"Failed to save timeseries for idx={idx}: {e}")
                # CSV 에러 필드에도 기록
                if result["error"] is None:
                    result["error"] = f"Timeseries save failed: {e}"

        # CSV 행 생성
        # 기존 행이 있으면 그것을 기반으로 하고, 없으면 새로 생성
        if idx in existing_rows:
            row = existing_rows[idx].copy()  # 기존 VAD 컬럼 유지
        else:
            row = {}

        # 새 결과 업데이트
        row.update({
            "idx": result["idx"],
            "band": result["band"],
            "song": result["song"],
            "duration_sec": result["duration_sec"],
            "speech_median": result["speech_median"],
            "speech_p10": result["speech_p10"],
            "speech_p90": result["speech_p90"],
            "speech_std": result["speech_std"],
            "n_frames": result["n_frames"],
            "error": result["error"]
        })
        existing_rows[idx] = row

    # 정렬해서 저장
    sorted_rows = [existing_rows[idx] for idx in sorted(existing_rows.keys())]

    with open(SPEECHINESS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    logger.info(f"Saved {len(sorted_rows)} rows to {SPEECHINESS_CSV}")

    # ========================================================================
    # SUMMARY
    # ========================================================================

    n_ok = sum(1 for r in results if r["error"] is None)
    n_err = len(results) - n_ok
    elapsed = time() - start_time

    logger.info(
        f"\n{'='*60}\n"
        f"DONE\n"
        f"  Total: {len(results)} songs\n"
        f"  Success: {n_ok}\n"
        f"  Error: {n_err}\n"
        f"  Elapsed: {elapsed/60:.1f}m\n"
        f"  Output: {SPEECHINESS_CSV}\n"
        f"  Timeseries: {TIMESERIES_DIR}\n"
        f"{'='*60}"
    )

if __name__ == "__main__":
    main()
