"""Bandori 전곡 라우드니스(loudness, LUFS) 피처 추출 스크립트.

ITU-R BS.1770 표준 기반 통합 LUFS, EBU R128 Loudness Range,
short-term(3초) loudness 시계열을 pyloudnorm 라이브러리로 계산한다.

실행 환경: Windows Python 3.13, pyloudnorm 0.2.0, soundfile 필수.

실행:
    python src/extract_loudness.py               # 전곡, 병렬(기본 8 worker)
    python src/extract_loudness.py --workers 10
    python src/extract_loudness.py --limit 5     # 앞 5곡만(테스트)
    python src/extract_loudness.py --idx 0,1,2   # 특정 idx만

중단해도 안전: 이미 out/loudness_raw.csv에 있는 idx는 건너뜀(resume).
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
# 경로 설정 (CONVENTIONS.md 준용)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent  # method-4-loudness/src/
_METHOD_DIR = _THIS_DIR.parent  # method-4-loudness/
_TOPIC_DIR = _METHOD_DIR.parent  # 20260731_audio_feats_revised/
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

_OUT_CSV = _METHOD_DIR / "out" / "csv" / "loudness_raw.csv"
_TS_DIR = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# 출력 컬럼 (순서 고정)
# ---------------------------------------------------------------------------
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "lufs_integrated",
    "lra",
    "st_median",
    "st_p10",
    "st_p90",
    "st_std",
    "mastering_flag",
    "extract_sec",
]

# 정규화된 스트리밍 타깃 LUFS (음원 마스터링 검출용)
MASTERING_TARGETS = [-14.0, -16.0, -23.0]
MASTERING_TOLERANCE = 0.3


def short_term_loudness(
    data: np.ndarray, rate: int, window_sec: float = 3.0
) -> np.ndarray:
    """3초 윈도우(50% 겹침, EBU R128 관례)로 short-term loudness 시계열 계산.

    -70 LUFS 이하 절대게이팅은 제외.

    Args:
        data: 모노 또는 스테레오 오디오 배열 (shape: (samples,) or (2, samples))
        rate: 샘플링 레이트 (Hz)
        window_sec: 윈도우 길이 (초, 기본 3.0)

    Returns:
        short-term LUFS 배열 (np.ndarray, 유효한 프레임만)
    """
    import pyloudnorm as pyln

    meter = pyln.Meter(rate)
    window_samples = int(window_sec * rate)
    hop_samples = window_samples // 2  # 50% 겹침

    loudness_values = []

    # 윈도우를 슬라이딩하며 계산
    for start in range(0, len(data) - window_samples + 1, hop_samples):
        frame = data[start : start + window_samples]
        try:
            loudness = meter.integrated_loudness(frame)
            # -70 LUFS 이하 절대게이팅으로 무음 구간 제외
            if loudness is not None and loudness > -70:
                loudness_values.append(loudness)
        except (ValueError, RuntimeError):
            # 너무 짧거나 무음인 프레임 스킵
            continue

    return np.array(loudness_values, dtype=np.float32)


def extract_features(path: Path) -> dict[str, float]:
    """단일 오디오 파일에서 라우드니스 피처 추출.

    Args:
        path: 오디오 파일 경로 (wav)

    Returns:
        피처 dict (lufs_integrated, lra, st_median, st_p10, st_p90, st_std,
        mastering_flag, duration_sec)
    """
    import pyloudnorm as pyln
    import soundfile as sf

    # 오디오 로드
    data, sr = sf.read(str(path), dtype=np.float32)
    dur = float(len(data) / sr)

    # 스테레오 → 모노 변환 (필요하면)
    if data.ndim == 2:
        data = data.mean(axis=1)

    # 통합 라우드니스 (Integrated Loudness)
    meter = pyln.Meter(sr)
    lufs_integrated = meter.integrated_loudness(data)

    # short-term loudness 시계열
    st = short_term_loudness(data, sr, window_sec=3.0)

    # short-term loudness 배열이 너무 짧으면 예외 처리
    if len(st) < 2:
        # 곡이 너무 짧거나 무음인 경우
        st_median = st_p10 = st_p90 = st_std = float("nan")
        lra = float("nan")
    else:
        st_median = float(np.median(st))
        st_p10 = float(np.percentile(st, 10))
        st_p90 = float(np.percentile(st, 90))
        st_std = float(np.std(st))
        lra = st_p90 - st_p10  # EBU R128 Loudness Range

    # 마스터링 플래그: lufs_integrated이 흔한 스트리밍 타깃 근처에 몰려있는지 확인
    mastering_flag = 0
    if lufs_integrated is not None and not np.isnan(lufs_integrated):
        for target in MASTERING_TARGETS:
            if abs(lufs_integrated - target) < MASTERING_TOLERANCE:
                mastering_flag = 1
                break

    return {
        "duration_sec": round(dur, 2),
        "lufs_integrated": lufs_integrated if lufs_integrated is not None else float("nan"),
        "lra": lra,
        "st_median": st_median,
        "st_p10": st_p10,
        "st_p90": st_p90,
        "st_std": st_std,
        "mastering_flag": mastering_flag,
    }


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path) → 결과 행 dict.

    실패해도 죽지 않고 error 필드를 담아 반환한다.
    """
    idx, band, song, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path))
        feats["extract_sec"] = round(time.time() - t0, 2)
        return {"idx": idx, "band": band, "song": song, "error": "", **feats}
    except Exception as exc:  # noqa: BLE001
        return {"idx": idx, "band": band, "song": song, "error": repr(exc)}


def _load_master() -> list[dict[str, str]]:
    """songs_master.csv 로드."""
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx(정상 행) 조회 (resume 근거)."""
    if not _OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with _OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # lufs_integrated이 채워진(=정상) 행만 done으로 간주
            if (r.get("lufs_integrated") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _audio_path(band: str, idx: int) -> Path:
    """오디오 파일 경로 조립."""
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _build_tasks(
    rows: list[dict[str, str]],
    done: set[int],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str, str]]:
    """처리할 작업 리스트 빌드."""
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
            print(
                f"  [WARN] 오디오 없음 idx={idx} {path.name} — 건너뜀", flush=True
            )
            continue
        tasks.append((idx, band, r["song"], str(path)))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _open_writer(append: bool):
    """CSV writer 생성."""
    header_needed = not (_OUT_CSV.exists() and _OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = _OUT_CSV.open(mode, encoding="utf-8", newline="")
    cols = FEATURE_COLUMNS + ["error"]
    writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def main() -> None:
    """메인 실행 함수."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description="라우드니스(LUFS) 피처 추출 (resumable, 병렬)")
    ap.add_argument("--workers", type=int, default=8, help="병렬 worker 수(기본 8)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

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
            it = (_worker(t) for t in tasks)
        else:
            import multiprocessing as mp

            pool = mp.Pool(processes=args.workers)
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

    print(
        f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분",
        flush=True,
    )
    print(f"산출: {_OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
