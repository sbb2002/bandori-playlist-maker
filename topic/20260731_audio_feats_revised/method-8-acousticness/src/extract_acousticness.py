"""Bandori 리듬게임 곡 661개의 어쿠스틱 피처 추출 스크립트.

Essentia 사전학습 mood_acoustic 분류기(MusiCNN 백본)를 사용해 2단계 파이프라인으로 분석한다:
1. TensorflowPredictMusiCNN으로 오디오 임베딩 추출 (패치 단위)
2. TensorflowPredict2D로 임베딩에서 mood_acoustic 분류(acoustic vs non_acoustic)

산출물
------
`out/csv/acousticness_raw.csv` — idx별 acoustic 요약통계 및 메타정보.
`out/timeseries/<idx>_acoustic.npy` — 패치별 acoustic 클래스 확률 시계열(1D float32).

주의
----
- WSL2 필요: Essentia 의존. 이 환경에 미설치된 경우 안내 후 조기 종료.
- 오디오 파일은 저작물 → 읽기 전용. 절대 이동/삭제 금지.
- 쓰기 대상: `out/csv/acousticness_raw.csv`, `out/timeseries/*.npy` 뿐.

실행
----
    python src/extract_acousticness.py \\
        --embedding-model-path /path/to/msd-musicnn-1.pb \\
        --model-path /path/to/mood_acoustic-msd-musicnn-1.pb
    python src/extract_acousticness.py --workers 8 --embedding-model-path ... --model-path ...
    python src/extract_acousticness.py --limit 10 --embedding-model-path ... --model-path ...
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Essentia 모듈 확인 (의존성 검사)
# ---------------------------------------------------------------------------
try:
    import essentia
    from essentia.standard import MonoLoader, TensorflowPredictMusiCNN, TensorflowPredict2D
    _ESSENTIA_AVAILABLE = True
except ImportError as e:
    _ESSENTIA_AVAILABLE = False
    _ESSENTIA_ERROR = str(e)

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent                    # method-8-acousticness/src/
_METHOD_DIR = _THIS_DIR.parent                                  # method-8-acousticness/
_TOPIC_DIR = _METHOD_DIR.parent                                 # 20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                              # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                            # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
OUT_CSV = _METHOD_DIR / "out" / "csv" / "acousticness_raw.csv"
TIMESERIES_DIR = _METHOD_DIR / "out" / "timeseries"

AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)

# 파일명: f"{band}__{idx:03d}.wav"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 16000  # Essentia mood_acoustic 모델 표준 샘플링 레이트

# 출력 컬럼 (순서 고정 → 재현/병합 안정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "acoustic_median",
    "acoustic_p10",
    "acoustic_p90",
    "acoustic_std",
    "n_patches",
    "extract_sec",
]

_EPS = 1e-9

# 워커 프로세스 내 모델 캐싱 (멀티프로세싱 전역변수)
_embedding_model_in_worker = None
_head_model_in_worker = None


def _init_worker(embedding_model_path: Path, head_model_path: Path) -> None:
    """워커 프로세스 초기화: 모델 로드 및 전역변수에 캐싱.

    Args:
        embedding_model_path: TensorflowPredictMusiCNN 모델 경로
        head_model_path: TensorflowPredict2D 분류 헤드 경로
    """
    global _embedding_model_in_worker, _head_model_in_worker
    _embedding_model_in_worker = TensorflowPredictMusiCNN(
        graphFilename=str(embedding_model_path),
        output="model/dense/BiasAdd"
    )
    _head_model_in_worker = TensorflowPredict2D(
        graphFilename=str(head_model_path),
        output="model/Softmax"
    )


def _check_essentia() -> None:
    """Essentia 설치 확인. 없으면 안내 후 조기 종료."""
    if not _ESSENTIA_AVAILABLE:
        print(
            "=" * 70,
            file=sys.stderr,
        )
        print(
            "[ERROR] Essentia 모듈을 찾을 수 없습니다.",
            file=sys.stderr,
        )
        print(
            "이 스크립트는 Essentia 사전학습 mood_acoustic 분류기를 필요합니다.",
            file=sys.stderr,
        )
        print(
            "",
            file=sys.stderr,
        )
        print(
            "WSL2 환경에서 다음과 같이 설치하세요:",
            file=sys.stderr,
        )
        print(
            "  pip install essentia-tensorflow",
            file=sys.stderr,
        )
        print(
            "",
            file=sys.stderr,
        )
        print(
            f"원본 에러: {_ESSENTIA_ERROR}",
            file=sys.stderr,
        )
        print(
            "=" * 70,
            file=sys.stderr,
        )
        sys.exit(1)


def extract_features(
    path: Path,
    embedding_model_path: Path,
    head_model_path: Path,
    embedding_model=None,
    head_model=None,
) -> dict[str, float | int]:
    """단일 오디오 파일에서 acoustic 확률 시계열을 추출해 요약통계를 반환.

    2단계 파이프라인:
    1. TensorflowPredictMusiCNN으로 mono 16kHz 오디오에서 임베딩 추출 (n_patches, 200)
    2. TensorflowPredict2D로 임베딩에서 mood_acoustic 분류 (n_patches, 2) [acoustic, non_acoustic]

    패치 길이는 모델이 내부적으로 결정하며, 일반적으로 약 3초 분량이다.

    Args:
        path: 오디오 파일 경로
        embedding_model_path: TensorflowPredictMusiCNN 모델 경로 (msd-musicnn-1.pb)
        head_model_path: TensorflowPredict2D 분류 헤드 경로 (mood_acoustic-msd-musicnn-1.pb)
        embedding_model: 사전 로드된 TensorflowPredictMusiCNN 모델 (None이면 경로에서 로드)
        head_model: 사전 로드된 TensorflowPredict2D 모델 (None이면 경로에서 로드)

    Returns:
        dict with keys:
            - duration_sec: 곡 길이(초)
            - acoustic_median, acoustic_p10, acoustic_p90, acoustic_std: 요약통계
            - n_patches: 패치 수
            - timeseries: 패치별 acoustic 확률 배열 (별도 저장용)
    """
    # 오디오 로드 (mono, 16kHz)
    loader = MonoLoader(filename=str(path), sampleRate=SR)
    y = loader()
    dur = float(len(y) / SR)

    # Step 1: 임베딩 추출 (모델 객체 재사용 또는 경로에서 로드)
    if embedding_model is None:
        embedding_model = TensorflowPredictMusiCNN(
            graphFilename=str(embedding_model_path),
            output="model/dense/BiasAdd"
        )
    embeddings = embedding_model(y)  # (n_patches, 200)

    # Step 2: 분류 예측 (모델 객체 재사용 또는 경로에서 로드)
    if head_model is None:
        head_model = TensorflowPredict2D(
            graphFilename=str(head_model_path),
            output="model/Softmax"
        )
    acoustic_probs_2col = head_model(embeddings)  # (n_patches, 2)

    # acoustic 확률 추출 (컬럼 0)
    acoustic_probs = acoustic_probs_2col[:, 0].astype(np.float32)
    n_patches = len(acoustic_probs)

    # 요약통계 계산
    return {
        "duration_sec": round(dur, 2),
        "acoustic_median": float(np.median(acoustic_probs)),
        "acoustic_p10": float(np.percentile(acoustic_probs, 10)),
        "acoustic_p90": float(np.percentile(acoustic_probs, 90)),
        "acoustic_std": float(np.std(acoustic_probs)),
        "n_patches": int(n_patches),
        "timeseries": acoustic_probs,
    }


def _worker(task: tuple[int, str, str, str, Path, Path]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path, embedding_model_path, head_model_path) → 결과 행 dict.

    워커 전역변수에 캐시된 모델을 사용한다. 실패해도 죽지 않고 error 필드를 담아 반환한다.
    """
    idx, band, song, path, embedding_model_path, head_model_path = task
    t0 = time.time()
    try:
        feats = extract_features(
            Path(path),
            embedding_model_path,
            head_model_path,
            embedding_model=_embedding_model_in_worker,
            head_model=_head_model_in_worker,
        )
        timeseries = feats.pop("timeseries")  # 별도 저장 대상
        feats["extract_sec"] = round(time.time() - t0, 2)
        result = {"idx": idx, "band": band, "song": song, "error": "", **feats}
        result["_timeseries"] = timeseries  # 내부 저장용
        return result
    except Exception as exc:  # noqa: BLE001 — 개별 곡 실패 격리
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "error": repr(exc),
            "_timeseries": None,
        }


def _load_master() -> list[dict[str, str]]:
    """songs_master.csv 로드."""
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx(정상 행)를 읽어 resume 근거로 삼는다."""
    if not OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # acoustic_median이 채워진(=정상) 행만 done으로 간주
            if (r.get("acoustic_median") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _audio_path(band: str, idx: int) -> Path:
    """오디오 파일 경로 생성."""
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _build_tasks(
    rows: list[dict[str, str]],
    done: set[int],
    only_idx: set[int] | None,
    limit: int | None,
    embedding_model_path: Path,
    head_model_path: Path,
) -> list[tuple[int, str, str, str, Path, Path]]:
    """처리할 곡 목록 생성."""
    tasks: list[tuple[int, str, str, str, Path, Path]] = []
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
        tasks.append((idx, band, r["song"], str(path), embedding_model_path, head_model_path))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _open_writer(append: bool) -> tuple:
    """CSV 파일 열기 및 writer 생성."""
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not (OUT_CSV.exists() and OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = OUT_CSV.open(mode, encoding="utf-8", newline="")
    cols = FEATURE_COLUMNS + ["error"]
    writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def _save_timeseries(idx: int, timeseries: np.ndarray, band: str = "") -> None:
    """패치별 acoustic 확률 시계열을 npy 파일로 저장."""
    TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"{band}__{idx:03d}" if band else f"{idx:03d}"
    out_path = TIMESERIES_DIR / f"{prefix}_acoustic.npy"  # band+idx: idx는 band 간 유일하지 않을 수 있음(2026-08-01 확인)
    np.save(str(out_path), timeseries)


def main() -> None:
    """메인 실행 함수."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    # Essentia 설치 확인
    _check_essentia()

    ap = argparse.ArgumentParser(
        description="Bandori 곡 어쿠스틱 피처 추출(Essentia, resumable, 병렬)"
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=4,
        help="병렬 worker 수(기본 4 — 모델 로딩 비용 높음)",
    )
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    ap.add_argument(
        "--embedding-model-path",
        type=str,
        required=True,
        help="TensorflowPredictMusiCNN 모델 경로 (msd-musicnn-1.pb)",
    )
    ap.add_argument(
        "--model-path",
        type=str,
        required=True,
        help="TensorflowPredict2D 분류 헤드 모델 경로 (mood_acoustic-msd-musicnn-1.pb)",
    )
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    embedding_model_path = Path(args.embedding_model_path)
    head_model_path = Path(args.model_path)

    if not embedding_model_path.exists():
        raise FileNotFoundError(f"임베딩 모델 파일 없음: {embedding_model_path}")
    if not head_model_path.exists():
        raise FileNotFoundError(f"mood_acoustic 모델 파일 없음: {head_model_path}")

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit, embedding_model_path, head_model_path)

    print(
        f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, 이번 처리 {len(tasks)}곡, "
        f"worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    append = not args.fresh
    # --idx 재추출 시에도 append(중복 idx는 build 단계에서 최신 우선 처리)
    f, writer = _open_writer(append=append)
    n_ok = n_err = 0
    t_start = time.time()
    try:
        if args.workers <= 1:
            # 순차 실행: 워커 초기화 후 직렬 처리
            _init_worker(embedding_model_path, head_model_path)
            it = (_worker(t) for t in tasks)
        else:
            import multiprocessing as mp

            # essentia-tensorflow가 내부적으로 CUDA 드라이버를 건드리므로 기본 fork
            # 방식은 fork 이후 CUDA/스레드 상태 불일치로 교착 상태에 빠진다(실측
            # 확인됨 — method-5-energy에서 동일 원인으로 100% 재현). spawn 사용.
            pool = mp.get_context("spawn").Pool(
                processes=args.workers,
                initializer=_init_worker,
                initargs=(embedding_model_path, head_model_path),
            )
            it = pool.imap_unordered(_worker, tasks)

        for i, res in enumerate(it, 1):
            # 시계열 저장(error 없을 때)
            if not res.get("error") and res.get("_timeseries") is not None:
                _save_timeseries(res["idx"], res["_timeseries"], band=res.get("band", ""))

            # 내부 저장용 필드 제거
            res.pop("_timeseries", None)

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

    print(
        f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분",
        flush=True,
    )
    print(f"산출: {OUT_CSV}", flush=True)
    if n_ok > 0:
        print(f"       {TIMESERIES_DIR}", flush=True)


if __name__ == "__main__":
    main()
