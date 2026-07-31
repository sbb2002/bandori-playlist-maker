"""liveness 통계적 보조 피처(노이즈플로어, RT60 추정) 추출 스크립트.

배경
----
PANNs liveness(Crowd/Applause/Cheering)의 보조 지표로:
- 노이즈플로어: 곡 내 배경 노이즈의 절대 레벨(dBFS)
- RT60: 곡 끝부분(마지막 노트 후) 음향 에너지의 감쇠 시간 추정

이 두 지표는 라이브 녹음의 음향 환경을 정량화한다.

구현 방식
---------
1. 노이즈플로어(noise_floor_db):
   - 트랙 전체 프레임별 RMS 계산(librosa)
   - 하위 10 percentile 구간의 중앙값 RMS
   - dBFS = 20 * log10(rms + eps)로 변환

2. RT60 추정(rt60_est_sec):
   - 곡 마지막 2초(또는 전체의 마지막 10%) 에너지 감쇠 구간 분석
   - 에너지 로그 데이터에 선형 회귀(감쇠 기울기 추정)
   - RT60_approx = 60dB / |기울기|
   - ⚠️ 이는 표준 잔향시간이 아니라 대략 근사치(온프레미스 마이크/스튜디오 음향
     측정용이 아님)

산출물
------
기존 liveness_raw.csv에 noise_floor_db와 rt60_est_sec 컬럼을 채워 덮어쓴다.
(또는 별도 CSV로 병합 - 현재는 extract_liveness_stat.py가 주 CSV 수정).

실행
----
    python src/extract_liveness_stat.py               # 전곡 처리
    python src/extract_liveness_stat.py --limit 5     # 앞 5곡만(테스트)
    python src/extract_liveness_stat.py --idx 0,1,2   # 특정 idx만
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import librosa
import numpy as np
from scipy import signal

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent
_REPO_ROOT = _TOPIC_DIR.parents[1]
_MYPROJECTS_ROOT = _REPO_ROOT.parent

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)

OUT_CSV = _METHOD_DIR / "out" / "liveness_raw.csv"

# 파라미터
SR = 22050  # 일반적인 분석용 SR
N_FFT = 2048
HOP = 512

_EPS = 1e-9


def estimate_noise_floor(y: np.ndarray, sr: int = SR, percentile: float = 10.0) -> float:
    """트랙 전체에서 노이즈플로어(하위 percentile RMS) 추정.

    Args:
        y: 오디오 시계열
        sr: 샘플링 레이트
        percentile: 하위 몇 percentile을 노이즈로 간주할지(기본 10)

    Returns:
        noise_floor_db: dBFS
    """
    # 프레임별 RMS
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    rms = librosa.feature.rms(S=S, frame_length=N_FFT, hop_length=HOP)[0]

    # 하위 percentile
    noise_rms = np.percentile(rms, percentile)
    noise_db = 20.0 * np.log10(noise_rms + _EPS)

    return float(noise_db)


def estimate_rt60(y: np.ndarray, sr: int = SR, tail_fraction: float = 0.1) -> float:
    """곡 끝부분 에너지 감쇠로 RT60 근사 추정.

    Schroeder 적분 개념 참고: 신호 끝부터 거슬러올라 누적 에너지 감소 곡선의
    기울기에서 60dB 감쇠 시간 추정.

    Args:
        y: 오디오 시계열
        sr: 샘플링 레이트
        tail_fraction: 곡 끝부분 비율(기본 0.1 = 10%)

    Returns:
        rt60_est_sec: 추정 잔향시간(초)
    """
    # 에너지 신호(스펙트로그램 전력)
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    power = S ** 2

    # 각 프레임의 전체 에너지(주파수 평균)
    energy = np.sum(power, axis=0)

    # 에너지가 거의 0이면 RT60 계산 불가
    if np.max(energy) < _EPS:
        return 0.0

    # 정규화(최대값 = 1)
    energy_norm = energy / (np.max(energy) + _EPS)

    # 곡 끝부분 추출
    tail_len = max(1, int(len(energy_norm) * tail_fraction))
    energy_tail = energy_norm[-tail_len:]

    # 로그 에너지(역시 정규화)
    energy_log = 10.0 * np.log10(energy_tail + _EPS)

    # 선형 회귀로 감쇠 기울기 추정
    x = np.arange(len(energy_log))
    if len(x) < 2:
        return 0.0

    # 다항식 피팅(1차 = 선형)
    coeffs = np.polyfit(x, energy_log, 1)
    slope = coeffs[0]  # dB/frame 단위

    # 프레임 → 초 변환
    hop_sec = HOP / sr
    slope_per_sec = slope / hop_sec  # dB/second

    # RT60 근사: 60dB 감쇠에 필요한 시간
    # ⚠️ slope_per_sec는 음수(에너지 감소)이므로 절대값 취함
    if abs(slope_per_sec) < _EPS:
        return 0.0

    rt60_approx = 60.0 / abs(slope_per_sec)

    # 상식적 범위: RT60 > 0.1초, < 5초(스튜디오 일반적)
    rt60_approx = np.clip(rt60_approx, 0.0, 5.0)

    return float(rt60_approx)


def extract_features(path: Path) -> dict[str, float]:
    """단일 오디오 파일의 통계 보조 피처 추출."""
    y, sr = librosa.load(str(path), sr=SR, mono=True)

    if len(y) == 0:
        raise ValueError("오디오 길이 0")

    noise_floor_db = estimate_noise_floor(y, sr=sr)
    rt60_est_sec = estimate_rt60(y, sr=sr)

    return {
        "noise_floor_db": round(noise_floor_db, 2),
        "rt60_est_sec": round(rt60_est_sec, 3),
    }


def _worker(task: tuple[int, str, str]) -> dict:
    """멀티프로세싱 worker."""
    idx, band, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path))
        return {"idx": idx, "band": band, "error": "", **feats}
    except Exception as exc:  # noqa: BLE001
        return {
            "idx": idx,
            "band": band,
            "noise_floor_db": "",
            "rt60_est_sec": "",
            "error": repr(exc),
        }


def _load_master() -> list[dict[str, str]]:
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _audio_path(band: str, idx: int) -> Path:
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _build_tasks(
    rows: list[dict[str, str]],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str]]:
    tasks = []
    for r in rows:
        idx = int(r["idx"])
        if only_idx is not None and idx not in only_idx:
            continue
        band = r["band"]
        path = _audio_path(band, idx)
        if not path.exists():
            print(f"  [WARN] 오디오 없음 idx={idx} {path.name} — 건너뜀", flush=True)
            continue
        tasks.append((idx, band, str(path)))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _read_existing_csv() -> dict[int, dict[str, str]]:
    """기존 CSV에서 행 읽기 (idx → row dict)."""
    if not OUT_CSV.exists():
        return {}
    existing = {}
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                idx = int(r["idx"])
                existing[idx] = r
            except (ValueError, KeyError):
                continue
    return existing


def _write_csv(rows: list[dict[str, str]]) -> None:
    """CSV 파일에 행들을 덮어쓰기."""
    if not rows:
        return

    # 첫 행의 키로 컬럼명 결정
    fieldnames = list(rows[0].keys())

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description="Liveness 통계 보조 피처 추출(노이즈플로어, RT60)")
    ap.add_argument("--workers", type=int, default=8, help="병렬 worker 수(기본 8)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    if not OUT_CSV.exists():
        print(f"ERROR: {OUT_CSV} 없음. extract_liveness_panns.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    tasks = _build_tasks(rows, only_idx, args.limit)

    print(
        f"전체 {len(rows)}곡, 이번 처리 {len(tasks)}곡, worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다.", flush=True)
        return

    # 기존 CSV 읽기
    existing = _read_existing_csv()
    print(f"기존 CSV 행 수: {len(existing)}", flush=True)

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
            idx = res["idx"]
            if idx in existing:
                # 기존 행 업데이트
                existing[idx].update(res)
            else:
                # 새 행 추가
                existing[idx] = res

            if res.get("error"):
                n_err += 1
                print(f"  [ERR] idx={idx} {res['error'][:80]}", flush=True)
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
        pass

    # 모든 행 정렬 후 쓰기(idx 순서)
    sorted_rows = [existing[idx] for idx in sorted(existing.keys())]
    _write_csv(sorted_rows)

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출(업데이트): {OUT_CSV} ({len(sorted_rows)}행)", flush=True)


if __name__ == "__main__":
    main()
