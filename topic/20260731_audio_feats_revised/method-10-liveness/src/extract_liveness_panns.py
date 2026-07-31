"""PANNs AudioTagging을 이용한 liveness 피처(Crowd/Applause/Cheering) 추출 스크립트.

배경 / 개념
-----------
liveness는 곡이 라이브 환경에서 녹음되었거나, 라이브 환경의 음향을 담고 있는 정도를 나타낸다.
PANNs(Pre-trained Audio Neural Networks) AudioSet 사전학습 모델의 Crowd/Applause/Cheering
클래스 확률을 조합해 liveness 점수를 산출한다.

무엇을 뽑는가
-------------
- PANNs AudioTagging으로 청크 단위 반복 추론으로 시간 시계열 구성
- Crowd, Applause, Cheering 클래스 확률의 평균 → crowd_series
- 요약통계: crowd_median, crowd_p10, crowd_p90, crowd_std
- 통계적 보조(noise_floor_db, rt60_est_sec)는 extract_liveness_stat.py에서 별도 추출
- 원시 시계열을 out/timeseries/<idx>_crowd.npy로 저장(재추론 없이 재집계 가능)

산출물
------
`out/liveness_raw.csv`:
  idx, band, song, duration_sec,
  crowd_median, crowd_p10, crowd_p90, crowd_std,
  noise_floor_db (extract_liveness_stat.py에서 채움),
  rt60_est_sec (extract_liveness_stat.py에서 채움),
  n_patches,
  error

`out/timeseries/<idx>_crowd.npy`: float32 1D array (청크 수,)

주의
----
- 오탐(false positive): 갱보컬, 곡 내 함성 이펙트 등이 오검출될 수 있음
  → 이 스크립트는 원시 확률만 뽑고, 청취 대조는 범위 밖(후속)
- PANNs는 clipwise_output만 제공하므로 2초 청크 단위로 반복 추론

실행
----
    python src/extract_liveness_panns.py               # 전곡, 병렬(기본 4)
    python src/extract_liveness_panns.py --workers 2
    python src/extract_liveness_panns.py --limit 3     # 앞 3곡만(테스트)
    python src/extract_liveness_panns.py --idx 0,1,2   # 특정 idx만 재추출
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import numpy as np
import torch

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 경로 (CONVENTIONS.md 규약)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # method-10-liveness/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-10-liveness/
_TOPIC_DIR = _METHOD_DIR.parent                       # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                    # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                  # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)

OUT_CSV = _METHOD_DIR / "out" / "liveness_raw.csv"
OUT_TIMESERIES_DIR = _METHOD_DIR / "out" / "timeseries"

# PANNs 파라미터
SR = 32000  # PANNs 요구 SR
MODEL_PATH = None  # None = 기본 경로, 자동 다운로드
CHUNK_LEN_SEC = 2.0  # 청크 길이(초)

# 출력 컬럼 (순서 고정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "crowd_median",
    "crowd_p10",
    "crowd_p90",
    "crowd_std",
    "noise_floor_db",  # extract_liveness_stat.py에서 채움
    "rt60_est_sec",    # extract_liveness_stat.py에서 채움
    "n_patches",
    "extract_sec",
]

_EPS = 1e-9


def _ensure_panns_data() -> None:
    """PANNs 클래스 라벨 및 체크포인트 다운로드."""
    panns_data_dir = Path.home() / "panns_data"
    labels_csv = panns_data_dir / "class_labels_indices.csv"
    checkpoint_path = panns_data_dir / "Cnn14_mAP=0.431.pth"

    panns_data_dir.mkdir(parents=True, exist_ok=True)

    # 클래스 라벨 다운로드
    if not labels_csv.exists():
        print(f"[INFO] PANNs 클래스 라벨 다운로드 중...", flush=True)
        try:
            url = "http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv"
            with urlopen(url, timeout=30) as response:
                with open(labels_csv, 'wb') as f:
                    f.write(response.read())
            print(f"[INFO] 클래스 라벨 다운로드 완료", flush=True)
        except Exception as exc:
            print(f"ERROR: 클래스 라벨 다운로드 실패: {exc}", file=sys.stderr)
            sys.exit(1)

    # 체크포인트 다운로드
    if not checkpoint_path.exists() or checkpoint_path.stat().st_size < 3e8:
        print(f"[INFO] PANNs 체크포인트 다운로드 중(~330MB)...", flush=True)
        try:
            url = "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1"
            with urlopen(url, timeout=300) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                with open(checkpoint_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (chunk_size * 100) == 0:
                            pct = (downloaded / total_size) * 100
                            print(f"  {pct:.1f}% ({downloaded / 1e6:.0f}MB / {total_size / 1e6:.0f}MB)",
                                  flush=True)
            print(f"[INFO] 체크포인트 다운로드 완료", flush=True)
        except Exception as exc:
            print(f"ERROR: 체크포인트 다운로드 실패: {exc}", file=sys.stderr)
            print(f"  수동 다운로드: https://zenodo.org/record/3987831", file=sys.stderr)
            sys.exit(1)


def _load_panns_model() -> tuple[Any, list[str]]:
    """PANNs AudioTagging 모델 로드 및 라벨 리스트 반환."""
    try:
        from panns_inference import AudioTagging, labels
    except ImportError:
        print(
            "ERROR: panns-inference not installed.\n"
            "  Run: pip install panns-inference\n"
            "  If download fails, check network access or run with --help.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        model = AudioTagging(checkpoint_path=MODEL_PATH,
                            device='cuda' if torch.cuda.is_available() else 'cpu')
        print(f"[INFO] PANNs 모델 로드 완료 (device={model.device})", flush=True)
        return model, labels
    except Exception as exc:
        print(
            f"ERROR: PANNs 체크포인트 로드 실패:\n  {exc}\n"
            "  네트워크 연결 확인 후 다시 시도하세요.",
            file=sys.stderr,
        )
        sys.exit(1)


def _find_target_indices(labels: list[str]) -> dict[str, int]:
    """labels 리스트에서 Crowd/Applause/Cheering 인덱스 찾기."""
    target_labels = ["Crowd", "Applause", "Cheering"]
    indices = {}
    for target in target_labels:
        # 정확한 매칭 시도
        for i, lbl in enumerate(labels):
            if lbl == target:
                indices[target] = i
                break

    if len(indices) < 3:
        missing = set(target_labels) - set(indices.keys())
        print(f"[WARN] 일부 대상 라벨 미발견: {missing}", flush=True)

    return indices


def extract_features(path: Path, model: Any, labels: list[str],
                    target_indices: dict[str, int]) -> dict[str, Any]:
    """단일 오디오 파일에서 liveness 피처를 추출.

    PANNs는 clipwise_output만 제공하므로, 오디오를 청크로 나누어 반복 추론.
    """
    import librosa

    # 오디오 로드
    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)

    if dur == 0:
        raise ValueError("오디오 길이 0")

    # 오디오를 청크로 나누어 반복 추론
    chunk_samples = int(CHUNK_LEN_SEC * sr)
    n_chunks = max(1, (len(y) + chunk_samples - 1) // chunk_samples)

    all_probs = []
    model.model.eval()

    for i in range(n_chunks):
        start = i * chunk_samples
        end = min((i + 1) * chunk_samples, len(y))
        chunk = y[start:end]

        # 배치 형태로 변환 및 device로 옮김
        chunk_tensor = torch.from_numpy(chunk[np.newaxis, :]).float()
        chunk_tensor = chunk_tensor.to(model.device)

        # 추론
        with torch.no_grad():
            output_dict = model.model(chunk_tensor, None)
            clipwise = output_dict.get("clipwise_output")  # (1, 527)

        if clipwise is not None:
            if isinstance(clipwise, torch.Tensor):
                clipwise = clipwise.cpu().numpy()
            all_probs.append(clipwise[0])  # (527,)

    if not all_probs:
        raise ValueError("PANNs 추론 실패")

    # (n_chunks, n_classes)로 스택
    all_probs = np.array(all_probs)  # (n_chunks, 527)

    # Crowd/Applause/Cheering 클래스 확률 추출 및 평균
    crowd_probs_per_chunk = []
    for cls_name, cls_idx in target_indices.items():
        if cls_idx < all_probs.shape[1]:
            crowd_probs_per_chunk.append(all_probs[:, cls_idx])

    if not crowd_probs_per_chunk:
        raise ValueError(f"유효한 Crowd 클래스 없음: {target_indices}")

    # 청크별 평균 (각 청크에서 3개 클래스의 평균)
    crowd_series = np.mean(np.stack(crowd_probs_per_chunk, axis=0), axis=0).astype(np.float32)

    # 요약통계
    crowd_median = float(np.median(crowd_series))
    crowd_p10 = float(np.percentile(crowd_series, 10))
    crowd_p90 = float(np.percentile(crowd_series, 90))
    crowd_std = float(np.std(crowd_series))

    n_patches = int(len(crowd_series))

    return {
        "duration_sec": round(dur, 2),
        "crowd_median": crowd_median,
        "crowd_p10": crowd_p10,
        "crowd_p90": crowd_p90,
        "crowd_std": crowd_std,
        "n_patches": n_patches,
        "timeseries": crowd_series,  # 별도 저장용(CSV에는 쓰지 않음)
    }


_model_in_worker: Any = None
_labels_in_worker: list[str] | None = None
_target_indices_in_worker: dict[str, int] | None = None


def _init_worker() -> None:
    """워커 프로세스 시작 시 1회만 PANNs 모델을 로드한다 — functools.partial로 모델을
    태스크마다 넘기면 태스크 수만큼 재직렬화(pickle)돼 661곡 규모에서 느려진다."""
    global _model_in_worker, _labels_in_worker, _target_indices_in_worker
    _model_in_worker, _labels_in_worker = _load_panns_model()
    _target_indices_in_worker = _find_target_indices(_labels_in_worker)


def _worker(task: tuple[int, str, str, str], model: Any = None, labels: list[str] | None = None,
            target_indices: dict[str, int] | None = None) -> dict:
    """멀티프로세싱 worker (idx, band, song, path) → 결과 행 dict.

    workers<=1일 때는 main()이 로드한 model/labels/target_indices를 인자로 받고,
    workers>1일 때는 _init_worker가 채운 전역(_model_in_worker 등)을 사용한다.
    """
    if model is None:
        model = _model_in_worker
        labels = _labels_in_worker
        target_indices = _target_indices_in_worker
    idx, band, song, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path), model, labels, target_indices)
        timeseries = feats.pop("timeseries")
        feats["extract_sec"] = round(time.time() - t0, 2)

        # timeseries를 .npy로 별도 저장
        ts_file = OUT_TIMESERIES_DIR / f"{idx:03d}_crowd.npy"
        np.save(str(ts_file), timeseries)

        return {"idx": idx, "band": band, "song": song, "error": "", **feats}
    except Exception as exc:  # noqa: BLE001
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "error": repr(exc),
            "duration_sec": "",
            "crowd_median": "",
            "crowd_p10": "",
            "crowd_p90": "",
            "crowd_std": "",
            "n_patches": "",
            "extract_sec": round(time.time() - t0, 2),
        }


def _load_master() -> list[dict[str, str]]:
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx를 읽어 resume 근거로 삼는다."""
    if not OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("crowd_median") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _audio_path(band: str, idx: int) -> Path:
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


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
        path = _audio_path(band, idx)
        if not path.exists():
            print(f"  [WARN] 오디오 없음 idx={idx} {path.name} — 건너뜀", flush=True)
            continue
        tasks.append((idx, band, r["song"], str(path)))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _open_writer(append: bool):
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

    # 멀티프로세싱 전에 한 번만 데이터 확인 및 모델 로드
    _ensure_panns_data()

    ap = argparse.ArgumentParser(description="PANNs Liveness 피처 추출 (resumable, 병렬)")
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4, 모델 메모리로 낮음)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    # PANNs 모델 로드 (메인 프로세스에서만)
    print("[INFO] PANNs 모델 로드 중...", flush=True)
    model, labels = _load_panns_model()

    # 대상 라벨 인덱스 찾기
    target_indices = _find_target_indices(labels)
    if not target_indices:
        print("ERROR: Crowd/Applause/Cheering 클래스를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] 대상 클래스 인덱스: {target_indices}", flush=True)

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit)

    print(
        f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, 이번 처리 {len(tasks)}곡, "
        f"worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    append = not args.fresh
    f, writer = _open_writer(append=append)
    n_ok = n_err = 0
    t_start = time.time()
    try:
        if args.workers <= 1:
            it = (_worker(t, model, labels, target_indices) for t in tasks)
        else:
            import multiprocessing as mp

            # 워커 프로세스마다 시작 시 1회 모델 로드(initializer) — functools.partial로
            # 모델을 매 태스크마다 넘기면 태스크 수만큼 재직렬화돼 비효율적.
            pool = mp.Pool(processes=args.workers, initializer=_init_worker)
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
    print(f"시계열: {OUT_TIMESERIES_DIR}/<idx>_crowd.npy", flush=True)


if __name__ == "__main__":
    main()
