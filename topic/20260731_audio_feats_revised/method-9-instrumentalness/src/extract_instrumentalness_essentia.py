"""Essentia voice_instrumental 분류기 기반 instrumentalness 피처 추출 (WSL2 전용).

배경 / 개념
-----------
Essentia의 사전학습된 voice_instrumental 심층신경망 분류기를 이용해 음성(voice) 확률을
프레임 단위로 계산하고, 그 시계열의 요약통계(median, p10, p90, std)를 산출한다:
  - voice 확률이 높음 = 음성 주도 = instrumentalness 낮음
  - voice 확률이 낮음 = 악기 주도 = instrumentalness 높음

산출물
------
`out/instrumentalness_raw.csv` — idx별 원시 피처(앞의 stem 버전과 idx 기준 병합):
  - voice_median, voice_p10, voice_p90, voice_std: Essentia 분류기 확률의 요약통계(0~1)
  - n_patches: 처리된 프레임/패치 개수

`out/timeseries/<idx>_voice.npy`: Essentia 분류기 프레임별 음성 확률 시계열(재추론 없이 재집계 가능).

주의
----
- **WSL2 필수**: Essentia 라이브러리 필요 (이 환경에서는 미설치).
- 이 환경에서 실행 시 import 실패 안내 후 조기 종료(sys.exit(1)) — 스크립트가 죽지 않도록
  최상단 try-except로 감싼다.

실행 (WSL2 환경)
----------------
    python src/extract_instrumentalness_essentia.py \
        --embedding-model-path /path/to/msd-musicnn-1.pb \
        --model-path /path/to/voice_instrumental-msd-musicnn-1.pb

    # 병렬 워커 4개
    python src/extract_instrumentalness_essentia.py \
        --embedding-model-path /path/to/msd-musicnn-1.pb \
        --model-path /path/to/voice_instrumental-msd-musicnn-1.pb \
        --workers 4

    # 처리 곡 수 제한
    python src/extract_instrumentalness_essentia.py \
        --embedding-model-path /path/to/msd-musicnn-1.pb \
        --model-path /path/to/voice_instrumental-msd-musicnn-1.pb \
        --limit 10

    # 특정 idx만 재추출
    python src/extract_instrumentalness_essentia.py \
        --embedding-model-path /path/to/msd-musicnn-1.pb \
        --model-path /path/to/voice_instrumental-msd-musicnn-1.pb \
        --idx 0,1,2
"""

from __future__ import annotations

import sys

# WSL2 환경 체크: Essentia import 실패 시 즉시 종료
try:
    import essentia
    from essentia.standard import (
        MonoLoader,
        TensorflowPredictMusiCNN,
        TensorflowPredict2D,
    )
except ImportError as e:
    print(
        "[오류] Essentia 라이브러리를 찾을 수 없습니다.",
        file=sys.stderr,
    )
    print(
        "이 스크립트는 WSL2 환경에서만 실행 가능합니다(Essentia 설치 필요).",
        file=sys.stderr,
    )
    print(f"상세: {e}", file=sys.stderr)
    sys.exit(1)

import argparse
import csv
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent  # method-9-*/src/
_METHOD_DIR = _THIS_DIR.parent  # method-9-*/
_TOPIC_DIR = _METHOD_DIR.parent  # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]  # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent  # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-song-sorter"
    / "src"
    / "content"
    / "cluster"
    / "audio_full"
)

OUT_CSV = _METHOD_DIR / "out" / "csv" / "instrumentalness_raw.csv"
TIMESERIES_DIR = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 16000  # MusiCNN 모델 기본 샘플레이트(essentia 내부에서 resampling 자동 처리)

# 출력 컬럼 (순서 고정, stem 버전과 동일)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "instr_stem_ratio",  # (stem 버전에서 채움)
    "voice_median",
    "voice_p10",
    "voice_p90",
    "voice_std",
    "n_patches",
]


def _agg_voice_probs(voice_probs: np.ndarray) -> dict[str, float]:
    """음성 확률 시계열의 요약통계 계산 (median, p10, p90, std)."""
    return {
        "voice_median": float(np.median(voice_probs)),
        "voice_p10": float(np.percentile(voice_probs, 10)),
        "voice_p90": float(np.percentile(voice_probs, 90)),
        "voice_std": float(np.std(voice_probs)),
        "n_patches": len(voice_probs),
    }


# 워커 프로세스별 전역 모델 캐시
_embedding_model_in_worker = None
_head_model_in_worker = None


def _init_worker(
    embedding_model_path: str,
    head_model_path: str,
) -> None:
    """워커 프로세스 초기화: 모델을 전역 변수에 로드(1회만)."""
    global _embedding_model_in_worker, _head_model_in_worker
    _embedding_model_in_worker = TensorflowPredictMusiCNN(
        graphFilename=embedding_model_path,
        output="model/dense/BiasAdd",
    )
    _head_model_in_worker = TensorflowPredict2D(
        graphFilename=head_model_path,
        output="model/Softmax",
    )


def extract_features(audio_path: Path) -> dict[str, float]:
    """단일 오디오 파일에서 Essentia voice_instrumental 분류 결과를 추출.

    2단계 파이프라인:
      1. TensorflowPredictMusiCNN: 오디오 → (n_patches, 200) 임베딩 자동 추출
         (내부적으로 mel-spectrogram 계산 + 187프레임 패치화 모두 처리)
      2. TensorflowPredict2D: 임베딩 → (n_patches, 2) 클래스 확률 [instrumental, voice]

    반환 값:
      - voice_median, voice_p10, voice_p90, voice_std: 음성 확률 요약통계
      - n_patches: 처리된 패치 개수
      또는 error 필드가 채워짐.
    """
    try:
        # 1단계: 오디오 로드 및 임베딩 추출
        loader = MonoLoader(filename=str(audio_path), sampleRate=SR)
        audio = loader()

        embeddings = _embedding_model_in_worker(audio)  # (n_patches, 200)

        # 2단계: voice_instrumental 분류
        voice_preds_2col = _head_model_in_worker(embeddings)  # (n_patches, 2)

        # 클래스 순서: [instrumental, voice]
        # voice 확률은 컬럼 1 (인덱스 1)
        voice_probs = voice_preds_2col[:, 1]

        if len(voice_probs) == 0:
            return {"error": "no_predictions"}

        stats = _agg_voice_probs(voice_probs)
        return stats

    except Exception as exc:
        return {"error": repr(exc)}


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path) → 결과 행 dict."""
    idx, band, song, path = task
    try:
        feats = extract_features(Path(path))
        if "error" in feats:
            return {"idx": idx, "band": band, "song": song, "error": feats["error"]}
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": "",  # 이미 stem 버전에서 채워짐
            "instr_stem_ratio": "",  # 이미 stem 버전에서 채워짐
            "voice_median": feats.get("voice_median", ""),
            "voice_p10": feats.get("voice_p10", ""),
            "voice_p90": feats.get("voice_p90", ""),
            "voice_std": feats.get("voice_std", ""),
            "n_patches": feats.get("n_patches", ""),
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "error": repr(exc),
        }


def _load_master() -> list[dict[str, str]]:
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _audio_path(band: str, idx: int) -> Path:
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _done_idxs() -> set[int]:
    """이미 essentia 추론 완료된 idx를 읽어 resume 근거로 삼는다."""
    if not OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # voice_median이 채워진(=정상) 행만 done으로 간주
            if (r.get("voice_median") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _build_tasks(
    rows: list[dict[str, str]],
    done: set[int],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str, str]]:
    """처리할 곡 태스크 생성. 오디오 파일 존재 여부로 필터링."""
    tasks: list[tuple[int, str, str, str]] = []
    for r in rows:
        idx = int(r["idx"])
        if only_idx is not None and idx not in only_idx:
            continue
        if only_idx is None and idx in done:
            continue
        band = r["band"]
        file_idx = int(r.get("file_idx", idx))  # 오디오 파일명 번호(2026-08-01: idx와 분리)
        path = _audio_path(band, file_idx)
        if not path.exists():
            print(f"  [WARN] 오디오 없음 idx={idx} {path.name} — 건너뜀", flush=True)
            continue
        tasks.append((idx, band, r["song"], str(path)))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _merge_or_create_csv(append: bool):
    """CSV 파일을 병합 또는 새로 생성하는 writer 반환.

    이미 존재하는 행은 유지하되, essentia 컬럼만 업데이트한다.
    """
    header_needed = not (OUT_CSV.exists() and OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = OUT_CSV.open(mode, encoding="utf-8", newline="")
    cols = FEATURE_COLUMNS + ["error"]
    writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(
        description="Essentia voice_instrumental 분류 기반 instrumentalness 추출(WSL2)"
    )
    ap.add_argument(
        "--embedding-model-path",
        type=str,
        required=True,
        help="MusiCNN 임베딩 모델 경로 (msd-musicnn-1.pb)",
    )
    ap.add_argument(
        "--model-path",
        type=str,
        required=True,
        help="voice_instrumental head 모델 경로 (voice_instrumental-msd-musicnn-1.pb)",
    )
    ap.add_argument("--workers", type=int, default=2, help="병렬 worker 수(기본 2)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not MASTER_CSV.exists():
        raise FileNotFoundError(f"songs_master.csv 없음: {MASTER_CSV}")

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    # 모델 경로 검증
    embedding_model_path = Path(args.embedding_model_path)
    head_model_path = Path(args.model_path)

    if not embedding_model_path.exists():
        raise FileNotFoundError(
            f"임베딩 모델 없음: {embedding_model_path}"
        )

    if not head_model_path.exists():
        raise FileNotFoundError(
            f"voice_instrumental head 모델 없음: {head_model_path}"
        )

    # timeseries 디렉터리 생성
    TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit)

    print(
        f"전체 {len(rows)}곡, 이미완료(essentia) {len(done)}곡, "
        f"이번 처리 {len(tasks)}곡, worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    append = not args.fresh
    f, writer = _merge_or_create_csv(append=append)
    n_ok = n_err = 0
    t_start = time.time()
    try:
        if args.workers <= 1:
            # 순차 실행: _init_worker 호출 후 generator 사용
            _init_worker(str(embedding_model_path), str(head_model_path))
            it = (_worker(t) for t in tasks)
        else:
            import multiprocessing as mp

            # 병렬 실행: 각 워커에서 _init_worker 호출.
            # essentia-tensorflow가 내부적으로 CUDA 드라이버를 건드리므로 기본 fork
            # 방식은 fork 이후 CUDA/스레드 상태 불일치로 교착 상태에 빠진다(실측
            # 확인됨 — method-5-energy에서 동일 원인으로 100% 재현). spawn 사용.
            pool = mp.get_context("spawn").Pool(
                processes=args.workers,
                initializer=_init_worker,
                initargs=(str(embedding_model_path), str(head_model_path)),
            )
            it = pool.imap_unordered(_worker, tasks)

        for i, res in enumerate(it, 1):
            writer.writerow(res)
            f.flush()
            if res.get("error"):
                n_err += 1
                print(f"  [ERR] idx={res['idx']} {res['error'][:80]}", flush=True)
            else:
                n_ok += 1

            if i % 10 == 0 or i == len(tasks):
                el = time.time() - t_start
                rate = i / el if el > 0 else 0
                eta = (len(tasks) - i) / rate if rate > 0 else 0
                print(
                    f"  진행 {i}/{len(tasks)}  ok={n_ok} err={n_err}  "
                    f"{rate:.2f}곡/s  ETA {eta/60:.1f}분",
                    flush=True,
                )

        if args.workers > 1:
            pool.close()
            pool.join()
    finally:
        f.close()

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
