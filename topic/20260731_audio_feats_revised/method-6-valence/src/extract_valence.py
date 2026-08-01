"""Valence(긍정 감정) 추출 스크립트 (essentia-tensorflow/emoMusic DEAM 기반).

배경 / 문제
-----------
Bandori 661곡의 valence(긍정 감정 지표, 1~9)를 추출한다. essentia-tensorflow의
emoMusic/DEAM 2단계 회귀 모델(MusiCNN 임베딩→emoMusic 헤드)을 사용하고, 패치별 원시
시계열과 요약통계(median, p10, p90, std)를 산출한다.

무엇을 뽑는가
-------------
- valence_median, valence_p10, valence_p90, valence_std: 패치별 원시 valence 시계열의 요약통계
- n_patches: 패치(MusiCNN 윈도우) 개수 (진단용)
- duration_sec: 곡 길이(초)

산출물
------
`out/valence_raw.csv` — idx별 원시 valence 값 (증분 append, resume 가능).
`out/timeseries/<idx>_valence.npy` — 패치별 원시 valence 시계열(1D float array).

주의
----
- 이 환경(Windows)에는 essentia-tensorflow가 설치되지 않음. WSL2 필요.
  import 실패 시 명확한 안내 메시지 후 sys.exit(1).
- 오디오 파일은 저작물 → **읽기 전용**. 커밋/이동/삭제 금지.
- 쓰기 대상: `out/valence_raw.csv`, `out/timeseries/<idx>_valence.npy` 뿐.
- mode_score나 method-3-mode 출력을 valence 대용으로 참조/폴백하지 않는다.

실행
----
    python src/extract_valence.py \\
        --embedding-model-path /path/to/msd-musicnn-1.pb \\
        --model-path /path/to/emomusic-msd-musicnn-2.pb
    python src/extract_valence.py \\
        --embedding-model-path /path/to/msd-musicnn-1.pb \\
        --model-path /path/to/emomusic-msd-musicnn-2.pb \\
        --workers 2
    python src/extract_valence.py \\
        --embedding-model-path /path/to/msd-musicnn-1.pb \\
        --model-path /path/to/emomusic-msd-musicnn-2.pb \\
        --limit 20  # 앞 20곡만

중단해도 안전: 이미 `out/valence_raw.csv`에 있는 idx는 건너뛴다(resume).
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
# essentia 임포트 체크 (WSL2 필수)
# ---------------------------------------------------------------------------
_ESSENTIA_AVAILABLE = False
try:
    import essentia.standard as es
    _ESSENTIA_AVAILABLE = True
except ImportError:
    _ESSENTIA_AVAILABLE = False

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # method-6-valence/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-6-valence/
_TOPIC_DIR = _METHOD_DIR.parent                       # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                    # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                  # pyworks/

_MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
_AUDIO_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-song-sorter"
    / "src"
    / "content"
    / "cluster"
    / "audio_full"
)
_OUT_CSV = _METHOD_DIR / "out" / "csv" / "valence_raw.csv"
_TIMESERIES_DIR = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 16000  # essentia 모델 기본 샘플 레이트

# 출력 컬럼 (순서 고정 → 재현/병합 안정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "valence_median",
    "valence_p10",
    "valence_p90",
    "valence_std",
    "n_patches",
]


def load_model(embedding_path: Path, head_path: Path):
    """essentia-tensorflow 모델 로드 (2단계 파이프라인).

    emoMusic/DEAM valence 회귀는 2개 모델 조합으로 구성:
    1. MusiCNN 임베딩 모델(msd-musicnn-1.pb): 오디오 → (n_patches, 200)
    2. emoMusic 헤드 모델(emomusic-msd-musicnn-2.pb): 임베딩 → (n_patches, 2) [valence, arousal]

    매개변수
    --------
    embedding_path : Path
        MusiCNN 임베딩 모델 경로 (msd-musicnn-1.pb)
    head_path : Path
        emoMusic 헤드 모델 경로 (emomusic-msd-musicnn-2.pb)

    반환값
    ------
    tuple[TensorflowPredictMusiCNN, TensorflowPredict2D]
        (embedding_model, head_model) 튜플
    """
    # 모델 경로 검증
    if not embedding_path.exists():
        raise FileNotFoundError(f"임베딩 모델 파일 없음: {embedding_path}")
    if not head_path.exists():
        raise FileNotFoundError(f"헤드 모델 파일 없음: {head_path}")

    # 1단계: MusiCNN 임베딩 모델 로드
    embedding_model = es.TensorflowPredictMusiCNN(
        graphFilename=str(embedding_path), output="model/dense/BiasAdd"
    )

    # 2단계: emoMusic 회귀 헤드 로드
    head_model = es.TensorflowPredict2D(
        graphFilename=str(head_path), output="model/Identity"
    )

    return embedding_model, head_model


def extract_features(path: Path, model) -> dict[str, float | int]:
    """단일 오디오 파일에서 valence 시계열을 뽑아 dict로 반환.

    매개변수
    --------
    path : Path
        오디오 파일 경로
    model : tuple[TensorflowPredictMusiCNN, TensorflowPredict2D]
        (embedding_model, head_model) 튜플

    반환값
    ------
    dict
        duration_sec, valence_median, valence_p10, valence_p90, valence_std, n_patches
        + timeseries npy 파일이 자동 저장됨(TIMESERIES_DIR/<idx>_valence.npy)
    """
    embedding_model, head_model = model

    # 오디오 로드 (MonoLoader는 자동으로 16000 Hz로 리샘플링)
    loader = es.MonoLoader(filename=str(path), sampleRate=SR)
    audio = loader()

    # 곡 길이 계산
    duration_sec = float(len(audio) / SR)

    # 1단계: MusiCNN 임베딩 추출 (mono 16kHz → (n_patches, 200))
    embeddings = embedding_model(audio)
    if not isinstance(embeddings, np.ndarray):
        embeddings = np.array(embeddings, dtype=np.float32)

    # 2단계: emoMusic 헤드로 회귀 예측 ((n_patches, 200) → (n_patches, 2))
    preds = head_model(embeddings)  # shape: (n_patches, 2) [valence, arousal]
    if not isinstance(preds, np.ndarray):
        preds = np.array(preds, dtype=np.float32)

    # valence 컬럼(인덱스 0) 추출
    valence_series = preds[:, 0].astype(np.float32)  # shape: (n_patches,)

    # 요약통계 계산
    n_patches = len(valence_series)
    valence_median = float(np.median(valence_series))
    valence_p10 = float(np.percentile(valence_series, 10))
    valence_p90 = float(np.percentile(valence_series, 90))
    valence_std = float(np.std(valence_series))

    return {
        "duration_sec": round(duration_sec, 2),
        "valence_median": round(valence_median, 4),
        "valence_p10": round(valence_p10, 4),
        "valence_p90": round(valence_p90, 4),
        "valence_std": round(valence_std, 4),
        "n_patches": n_patches,
        "_timeseries": valence_series,  # 별도 처리용
    }


_model_in_worker = None


def _init_worker(model_paths: tuple[Path, Path]) -> None:
    """각 워커 프로세스가 시작될 때 1회만 모델을 로드한다(모델 객체를 매 태스크마다
    pickle해서 넘기지 않기 위함 — TensorFlow 그래프 객체는 보통 pickle 불가/비효율적).

    매개변수
    --------
    model_paths : tuple[Path, Path]
        (embedding_model_path, head_model_path)
    """
    global _model_in_worker
    embedding_path, head_path = model_paths
    _model_in_worker = load_model(embedding_path, head_path)


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path) → 결과 행 dict.

    모델은 _init_worker가 워커 프로세스 시작 시 채워둔 전역(_model_in_worker)을 사용한다.
    실패해도 죽지 않고 error 필드를 담아 반환한다(전체 배치 진행 보장).
    """
    idx, band, song, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path), _model_in_worker)
        timeseries = feats.pop("_timeseries")

        # Timeseries npy 저장
        _TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)
        ts_path = _TIMESERIES_DIR / f"{band}__{idx:03d}_valence.npy"  # band+idx: idx는 band 간 유일하지 않을 수 있음(2026-08-01 확인)
        np.save(str(ts_path), timeseries)

        feats["extract_sec"] = round(time.time() - t0, 2)
        return {"idx": idx, "band": band, "song": song, "error": "", **feats}
    except Exception as exc:  # noqa: BLE001 — 개별 곡 실패 격리
        return {"idx": idx, "band": band, "song": song, "error": repr(exc)}


def _load_master() -> list[dict[str, str]]:
    with _MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx(정상 행)를 읽어 resume 근거로 삼는다."""
    if not _OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with _OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # valence_median이 채워진(=정상) 행만 done으로 간주
            if (r.get("valence_median") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _audio_path(band: str, idx: int) -> Path:
    return _AUDIO_DIR / f"{band}__{idx:03d}.wav"


def _build_tasks(
    rows: list[dict[str, str]],
    done: set[int],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str, str]]:
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


def _open_writer(append: bool):
    header_needed = not (_OUT_CSV.exists() and _OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = _OUT_CSV.open(mode, encoding="utf-8", newline="")
    cols = FEATURE_COLUMNS + ["extract_sec", "error"]
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

    # essentia 가용성 확인
    if not _ESSENTIA_AVAILABLE:
        print(
            "\n[ERROR] essentia-tensorflow이 설치되지 않았습니다.",
            "이 스크립트는 WSL2 환경에서만 실행 가능합니다.",
            "WSL2에서 다음을 실행하세요:",
            "  pip install essentia-tensorflow",
            sep="\n",
            flush=True,
        )
        sys.exit(1)

    ap = argparse.ArgumentParser(
        description="essentia-tensorflow emoMusic/DEAM 기반 valence 추출(resumable, 병렬)"
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
        help="emoMusic 헤드 모델 경로 (emomusic-msd-musicnn-2.pb)",
    )
    ap.add_argument("--workers", type=int, default=2, help="병렬 worker 수(기본 2, 모델 로딩 비용 고려)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not _AUDIO_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {_AUDIO_DIR}")

    embedding_model_path = Path(args.embedding_model_path)
    model_path = Path(args.model_path)
    if not embedding_model_path.exists():
        raise FileNotFoundError(f"임베딩 모델 파일 없음: {embedding_model_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"헤드 모델 파일 없음: {model_path}")

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit)

    print(f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, 이번 처리 {len(tasks)}곡, "
          f"worker={args.workers}", flush=True)
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    append = not args.fresh
    f, writer = _open_writer(append=append)
    n_ok = n_err = 0
    t_start = time.time()
    try:
        model_paths = (embedding_model_path, model_path)
        if args.workers <= 1:
            _init_worker(model_paths)  # 메인 프로세스에서 1회 로드
            it = (_worker(t) for t in tasks)
        else:
            import multiprocessing as mp

            # 워커 프로세스마다 시작 시 1회 모델 로드(initializer) — 모델 객체를 매
            # 태스크마다 pickle해서 넘기지 않음(TF 그래프 pickle 불가/비효율 회피).
            # essentia-tensorflow가 내부적으로 CUDA 드라이버를 건드리므로 기본 fork
            # 방식은 fork 이후 CUDA/스레드 상태 불일치로 교착 상태에 빠진다(실측
            # 확인됨 — method-5-energy에서 동일 원인으로 100% 재현). spawn 사용.
            pool = mp.get_context("spawn").Pool(
                processes=args.workers, initializer=_init_worker, initargs=(model_paths,)
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
                print(f"  진행 {i}/{len(tasks)}  ok={n_ok} err={n_err}  "
                      f"{rate:.2f}곡/s  ETA {eta/60:.1f}분", flush=True)

        if args.workers > 1:
            pool.close()
            pool.join()
    finally:
        f.close()

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {_OUT_CSV}", flush=True)
    print(f"시계열: {_TIMESERIES_DIR}", flush=True)


if __name__ == "__main__":
    main()
