#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_energy.py — essentia-tensorflow 2단계 파이프라인(MusiCNN → emomusic)으로 energy(arousal) 추출.

의존성: essentia, essentia-tensorflow (WSL2 환경)
출력: out/energy_raw.csv + out/timeseries/<idx>_arousal.npy

실행:
  python src/extract_energy.py \
    --embedding-model-path /path/to/msd-musicnn-1.pb \
    --model-path /path/to/emomusic-msd-musicnn-2.pb \
    [--workers 4] [--limit 10]
"""

import sys
import os
import csv
import argparse
import logging
import multiprocessing as mp
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from time import time

import numpy as np
import pandas as pd

# ============================================================================
# ESSENTIA IMPORT HANDLING
# ============================================================================

try:
    import essentia.standard as es
    from essentia import Pool as EssentiaPool
    import essentia
    ESSENTIA_AVAILABLE = True
except ImportError as e:
    ESSENTIA_AVAILABLE = False
    ESSENTIA_ERROR = str(e)

if not ESSENTIA_AVAILABLE:
    print(
        "ERROR: essentia-tensorflow 미설치 또는 import 실패.\n"
        "이 스크립트는 WSL2 환경에서만 실행 가능합니다.\n"
        "WSL2에서 다음 명령으로 설치한 후 다시 시도하세요:\n"
        "  pip install essentia essentia-tensorflow\n"
        f"\n상세 에러:\n{ESSENTIA_ERROR}"
    )
    sys.exit(1)

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

_THIS_DIR = Path(__file__).resolve().parent          # method-5-energy/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-5-energy/
_TOPIC_DIR = _METHOD_DIR.parent                       # 20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                    # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                  # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"

AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)
# 파일명: f"{band}__{idx:03d}.wav" (예: afterglow__000.wav) — 743개 존재

OUT_DIR = _METHOD_DIR / "out"
TIMESERIES_DIR = OUT_DIR / "timeseries"
ENERGY_CSV = OUT_DIR / "energy_raw.csv"

# ============================================================================
# MODEL LOADING
# ============================================================================

_model_cache = {}

def load_model(embedding_path: Path, head_path: Path):
    """
    essentia-tensorflow 2단계 모델 로드:
      1. MusiCNN 임베딩 추출 모델
      2. emomusic 회귀 헤드 모델

    Args:
        embedding_path: MusiCNN 임베딩 모델 파일 경로 (.pb).
        head_path: emomusic 헤드 회귀 모델 파일 경로 (.pb).

    Returns:
        (embedding_model, head_model) tuple. 각 모델은 callable 객체.
        - embedding_model(audio_mono_16k) → (n_patches, 200) ndarray
        - head_model(embeddings) → (n_patches, 2) ndarray [valence, arousal]

    Note:
        모델 로딩은 워커당 1회만 호출(성능).
        캐싱 후 재사용.
    """

    if "models" in _model_cache:
        return _model_cache["models"]

    try:
        logger.info(f"Loading MusiCNN embedding model from: {embedding_path}")
        embedding_model = es.TensorflowPredictMusiCNN(
            graphFilename=str(embedding_path),
            output="model/dense/BiasAdd"
        )

        logger.info(f"Loading emomusic head model from: {head_path}")
        head_model = es.TensorflowPredict2D(
            graphFilename=str(head_path),
            output="model/Identity"
        )

        models = (embedding_model, head_model)
        _model_cache["models"] = models
        logger.info("Both models loaded successfully")
        return models

    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        raise RuntimeError(f"Model loading failed: {e}")

# ============================================================================
# FEATURE EXTRACTION
# ============================================================================

def extract_features(audio_path: Path, model) -> dict:
    """
    단일 곡에서 arousal 시계열 + 요약통계 추출.

    2단계 파이프라인:
      1. MusiCNN 모델(audio) → (n_patches, 200) 임베딩 배열
      2. emomusic 헤드 모델(embeddings) → (n_patches, 2) [valence, arousal]
      3. arousal 컬럼(인덱스 1)만 추출 → 1D 배열

    Args:
        audio_path: 오디오 파일 경로 (.wav).
        model: (embedding_model, head_model) tuple.

    Returns:
        dict with keys:
            - arousal_series: 1D ndarray (패치별 arousal 원시값)
            - arousal_median: float
            - arousal_p10: float
            - arousal_p90: float
            - arousal_std: float
            - n_patches: int (시계열 길이)
            - duration_sec: float
            - error: None (성공 시)
    """

    try:
        embedding_model, head_model = model

        # Essentia 모노 로더 (16kHz 재샘플)
        loader = es.MonoLoader(filename=str(audio_path), sampleRate=16000)
        audio = loader()

        logger.debug(f"Loaded audio from {audio_path}: {len(audio)} samples @ 16kHz")

        # 1단계: MusiCNN 임베딩 추출
        embeddings = embedding_model(audio)  # → (n_patches, 200)
        embeddings = np.asarray(embeddings, dtype=np.float32)
        logger.debug(f"Embeddings shape: {embeddings.shape}")

        # 2단계: emomusic 헤드 회귀 예측
        preds = head_model(embeddings)  # → (n_patches, 2) [valence, arousal]
        preds = np.asarray(preds, dtype=np.float32)
        logger.debug(f"Predictions shape: {preds.shape}")

        # 3단계: arousal 컬럼(인덱스 1) 추출
        arousal_series = preds[:, 1]  # 1D ndarray

        n_patches = len(arousal_series)
        duration_sec = len(audio) / 16000.0  # 오디오 길이 (초)

        # 요약통계
        arousal_median = float(np.median(arousal_series))
        arousal_p10 = float(np.percentile(arousal_series, 10))
        arousal_p90 = float(np.percentile(arousal_series, 90))
        arousal_std = float(np.std(arousal_series))

        return {
            "arousal_series": arousal_series,
            "arousal_median": arousal_median,
            "arousal_p10": arousal_p10,
            "arousal_p90": arousal_p90,
            "arousal_std": arousal_std,
            "n_patches": n_patches,
            "duration_sec": duration_sec,
            "error": None
        }

    except Exception as e:
        logger.warning(f"Error extracting features from {audio_path}: {e}")
        return {
            "arousal_series": None,
            "arousal_median": None,
            "arousal_p10": None,
            "arousal_p90": None,
            "arousal_std": None,
            "n_patches": None,
            "duration_sec": None,
            "error": str(e)
        }

# ============================================================================
# WORKER (multiprocessing)
# ============================================================================

_model_in_worker = None

def _init_worker(embedding_path: Path, head_path: Path):
    """각 워커 프로세스에서 2단계 모델 로드."""
    global _model_in_worker
    _model_in_worker = load_model(embedding_path, head_path)

def _worker(task: dict) -> dict:
    """
    개별 곡 처리 워커.

    Args:
        task: dict with keys:
            - idx: int (곡 번호)
            - band: str
            - song: str
            - audio_path: Path

    Returns:
        dict with keys:
            - idx, band, song, duration_sec
            - arousal_median, arousal_p10, arousal_p90, arousal_std
            - n_patches
            - arousal_series (timeseries npy 저장용)
            - error
    """

    global _model_in_worker

    idx = task["idx"]
    band = task["band"]
    song = task["song"]
    audio_path = task["audio_path"]

    try:
        if not audio_path.exists():
            return {
                "idx": idx,
                "band": band,
                "song": song,
                "duration_sec": None,
                "arousal_median": None,
                "arousal_p10": None,
                "arousal_p90": None,
                "arousal_std": None,
                "n_patches": None,
                "arousal_series": None,
                "error": f"Audio file not found: {audio_path}"
            }

        result = extract_features(audio_path, _model_in_worker)

        # timeseries는 워커 프로세스 안에서 바로 저장한다(Pool IPC로 원시 배열을
        # 통째로 되돌려보내지 않기 위함 — 대용량 ndarray를 결과로 반환하면 멀티
        # 프로세싱 파이프에서 교착 상태를 유발하는 사례가 있었다).
        if result["arousal_series"] is not None:
            npy_path = TIMESERIES_DIR / f"{idx:03d}_arousal.npy"
            try:
                np.save(str(npy_path), result["arousal_series"])
            except Exception as e:
                if result["error"] is None:
                    result["error"] = f"Timeseries save failed: {e}"

        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": result["duration_sec"],
            "arousal_median": result["arousal_median"],
            "arousal_p10": result["arousal_p10"],
            "arousal_p90": result["arousal_p90"],
            "arousal_std": result["arousal_std"],
            "n_patches": result["n_patches"],
            "error": result["error"]
        }

    except Exception as e:
        logger.error(f"Worker crashed on idx={idx}: {e}")
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": None,
            "arousal_median": None,
            "arousal_p10": None,
            "arousal_p90": None,
            "arousal_std": None,
            "n_patches": None,
            "arousal_series": None,
            "error": f"Worker error: {e}"
        }

# ============================================================================
# RESUME SUPPORT
# ============================================================================

def get_done_idxs(csv_path: Path) -> set:
    """이미 처리된 idx 읽기."""
    if not csv_path.exists():
        return set()

    done_idxs = set()
    try:
        df = pd.read_csv(csv_path, usecols=["idx"])
        done_idxs = set(df["idx"].unique())
    except Exception as e:
        logger.warning(f"Failed to read done_idxs from {csv_path}: {e}")

    return done_idxs

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract arousal features using essentia-tensorflow 2-stage pipeline (MusiCNN → emomusic)."
    )
    parser.add_argument(
        "--embedding-model-path",
        type=Path,
        required=True,
        help="Path to MusiCNN embedding model (.pb checkpoint)"
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        required=True,
        help="Path to emomusic head regression model (.pb checkpoint)"
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
        help="Ignore existing output and restart from scratch"
    )

    args = parser.parse_args()

    # ========================================================================
    # SETUP
    # ========================================================================

    logger.info(f"Starting arousal extraction (method-5-energy)")
    logger.info(f"Embedding model: {args.embedding_model_path}")
    logger.info(f"Head model: {args.model_path}")
    logger.info(f"Workers: {args.workers}, Limit: {args.limit}, Fresh: {args.fresh}")

    # 모델 존재 여부 확인
    if not args.embedding_model_path.exists():
        logger.error(f"Embedding model file not found: {args.embedding_model_path}")
        sys.exit(1)

    if not args.model_path.exists():
        logger.error(f"Head model file not found: {args.model_path}")
        sys.exit(1)

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
    if ENERGY_CSV.exists() and not args.fresh:
        done_idxs = get_done_idxs(ENERGY_CSV)
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

        # 오디오 파일 경로: {band}__{idx:03d}.wav
        audio_filename = f"{band}__{idx:03d}.wav"
        audio_path = AUDIO_FULL_DIR / audio_filename

        tasks.append({
            "idx": idx,
            "band": band,
            "song": song,
            "audio_path": audio_path
        })

    # ========================================================================
    # PROCESS (multiprocessing)
    # ========================================================================

    logger.info(f"Starting multiprocessing with {args.workers} workers...")
    start_time = time()

    results = []
    # essentia-tensorflow가 내부적으로 CUDA 드라이버를 건드리기 때문에 기본 fork
    # 방식으로 워커를 만들면 fork 이후 CUDA/스레드 상태 불일치로 교착 상태에 빠진다
    # (실측 확인됨: fork에서 재현 100%, spawn에서 정상 동작). spawn 컨텍스트 사용.
    ctx = mp.get_context("spawn")
    with ctx.Pool(
        processes=args.workers,
        initializer=_init_worker,
        initargs=(args.embedding_model_path, args.model_path)
    ) as pool:
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

    logger.info(f"Saving results to {ENERGY_CSV}...")

    # CSV 레이아웃
    csv_fieldnames = [
        "idx", "band", "song", "duration_sec",
        "arousal_median", "arousal_p10", "arousal_p90", "arousal_std",
        "n_patches",
        "error"
    ]

    # 기존 CSV 읽기 (resume 시)
    existing_rows = {}
    if ENERGY_CSV.exists() and not args.fresh:
        try:
            with open(ENERGY_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    idx = int(row["idx"])
                    existing_rows[idx] = row
        except Exception as e:
            logger.warning(f"Failed to read existing CSV: {e}")

    # 새 결과 추가 (timeseries는 이미 _worker 안에서 저장 완료됨)
    for result in results:
        idx = result["idx"]
        # CSV 행 생성
        row = {
            "idx": result["idx"],
            "band": result["band"],
            "song": result["song"],
            "duration_sec": result["duration_sec"],
            "arousal_median": result["arousal_median"],
            "arousal_p10": result["arousal_p10"],
            "arousal_p90": result["arousal_p90"],
            "arousal_std": result["arousal_std"],
            "n_patches": result["n_patches"],
            "error": result["error"]
        }
        existing_rows[idx] = row

    # 정렬해서 저장
    sorted_rows = [existing_rows[idx] for idx in sorted(existing_rows.keys())]

    with open(ENERGY_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    logger.info(f"Saved {len(sorted_rows)} rows to {ENERGY_CSV}")

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
        f"  Output: {ENERGY_CSV}\n"
        f"  Timeseries: {TIMESERIES_DIR}\n"
        f"{'='*60}"
    )

if __name__ == "__main__":
    main()
