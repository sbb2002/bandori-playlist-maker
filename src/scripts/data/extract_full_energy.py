"""전곡(full-track) 지각 에너지(intensity) 피처 재추출 스크립트.

배경 / 문제
-----------
현재 곡 강도는 발췌 구간만 분석된 프록시(`energy_proxy`, `acousticness_proxy`)로
계산되어, **조용한 인트로에 속아** 실제로 시끄러운 곡(예: 処救生, 灼熱 Bonfire!,
はいよろこんで)을 조용하다고 오판한다. 로컬 전곡 wav에서 **곡 전체 기준**의 스펙트럼/
타악 피처를 뽑아 이 발췌 편향을 근본 해소한다.

R&D 근거: document-archive 브랜치 archive/research/2026-07-11-playlist-sequencing-strategy.md §5(재추출 권고 1).

무엇을 뽑는가 (전부 full-track, mean + p90/p95 두 집계)
------------------------------------------------------
- spectral_centroid / rolloff / bandwidth / flatness / contrast (밝기·시끄러움 스펙트럼)
- zero_crossing_rate (거칠기/노이지함)
- HPSS 타악 에너지 비율 perc (부장 프로토타입에서 가장 유망) — mean/p90/p95
- onset_strength(=spectral flux) + onset_rate (타격 밀도)
- rms (참고용 — 파일이 라우드니스 정규화돼 있어 절대값은 무용. 문서화 목적으로만 기록)

각 프레임 피처에 대해 **평균**과 **p90**(perc는 p95도)을 함께 기록해, "시끄러운 구간이
있으면 시끄럽게" 반영한다(발췌가 아닌 전곡 집계이므로 인트로만 조용한 곡을 잡아낸다).

산출물
------
`data/full_audio_features.csv` — idx별 원시 서브피처 (증분 append, resume 가능).
이 스크립트는 **원시 피처만** 뽑는다. 복합(composite) `energy_full` 산출·검증·
`songs_master.csv` 병합은 별도 스크립트 `build_energy_full.py`가 담당한다.

주의 (R6/R11)
-------------
- 오디오 파일은 저작물 → **읽기 전용**. 커밋/이동/삭제 금지.
- 쓰기 대상: `data/full_audio_features.csv` 뿐.

실행
----
    python src/scripts/data/extract_full_energy.py               # 전곡, 병렬(기본 8 worker)
    python src/scripts/data/extract_full_energy.py --workers 10
    python src/scripts/data/extract_full_energy.py --limit 20    # 앞 20곡만(테스트)
    python src/scripts/data/extract_full_energy.py --idx 278,272,512  # 특정 idx만

중단해도 안전: 이미 `full_audio_features.csv`에 있는 idx는 건너뛴다(resume).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")  # librosa/soundfile deprecation·UserWarning 소음 제거

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
# .../bandori-playlist-maker/src/scripts/data/ -> repo root = parents[3]
_REPO_ROOT = _THIS_DIR.parents[2]
_MYPROJECTS_ROOT = _REPO_ROOT.parent

_AUDIO_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-song-sorter"
    / "src"
    / "content"
    / "cluster"
    / "audio_full"
)
_MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
_OUT_CSV = _REPO_ROOT / "data" / "full_audio_features.csv"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 22050
N_FFT = 2048
HOP = 512

# 출력 컬럼 (순서 고정 → 재현/병합 안정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "cen_mean", "cen_p90",        # spectral centroid (밝기/고역 무게중심, Hz)
    "roll_mean", "roll_p90",      # spectral rolloff 85% (Hz)
    "bw_mean", "bw_p90",          # spectral bandwidth (Hz)
    "flat_mean", "flat_p90",      # spectral flatness (0~1, 노이즈성)
    "contrast_mean", "contrast_p90",  # spectral contrast (밴드 평균, dB)
    "zcr_mean", "zcr_p90",        # zero-crossing rate (거칠기)
    "perc_mean", "perc_p90", "perc_p95",  # HPSS 타악 에너지 비율 (0~1)
    "onset_mean", "onset_p90",    # onset strength (spectral flux)
    "onset_rate",                 # 초당 온셋 수
    "rms_mean", "rms_p90",        # RMS (참고용 — 정규화 파일이라 절대값 무의미)
    "extract_sec",                # 처리 소요(진단용)
]

_EPS = 1e-9


def _agg(x: np.ndarray, p: float = 90.0) -> tuple[float, float]:
    """(평균, p분위) 튜플."""
    return float(np.mean(x)), float(np.percentile(x, p))


def extract_features(path: Path) -> dict[str, float]:
    """단일 오디오 파일에서 전곡 서브피처를 뽑아 dict로 반환.

    STFT를 1회만 계산해 스펙트럼·HPSS·onset·rms를 모두 파생(효율).
    """
    import librosa  # worker 프로세스에서 import (spawn 안전)

    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)

    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))  # magnitude
    power = S ** 2

    cen = librosa.feature.spectral_centroid(S=S, sr=sr, n_fft=N_FFT, hop_length=HOP)[0]
    roll = librosa.feature.spectral_rolloff(
        S=S, sr=sr, n_fft=N_FFT, hop_length=HOP, roll_percent=0.85
    )[0]
    bw = librosa.feature.spectral_bandwidth(S=S, sr=sr, n_fft=N_FFT, hop_length=HOP)[0]
    flat = librosa.feature.spectral_flatness(S=S, n_fft=N_FFT, hop_length=HOP)[0]
    contrast = librosa.feature.spectral_contrast(
        S=S, sr=sr, n_fft=N_FFT, hop_length=HOP
    )  # (n_bands+1, frames)
    contrast_frame = contrast.mean(axis=0)  # 프레임별 밴드 평균 대비(dB)
    zcr = librosa.feature.zero_crossing_rate(
        y, frame_length=N_FFT, hop_length=HOP
    )[0]
    rms = librosa.feature.rms(S=S, frame_length=N_FFT, hop_length=HOP)[0]

    # HPSS 타악 비율 (프레임별): perc = ||P||^2 / (||H||^2 + ||P||^2)
    H, P = librosa.decompose.hpss(S)
    hpow = (H ** 2).sum(axis=0)
    ppow = (P ** 2).sum(axis=0)
    perc = ppow / (hpow + ppow + _EPS)

    # onset strength (= half-wave rectified spectral flux), mel 기반(표준)
    mel = librosa.feature.melspectrogram(S=power, sr=sr, n_fft=N_FFT, hop_length=HOP)
    onset_env = librosa.onset.onset_strength(
        S=librosa.power_to_db(mel, ref=np.max), sr=sr, hop_length=HOP
    )
    onsets = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=HOP
    )
    onset_rate = float(len(onsets) / dur) if dur > 0 else 0.0

    cen_m, cen_p = _agg(cen)
    roll_m, roll_p = _agg(roll)
    bw_m, bw_p = _agg(bw)
    flat_m, flat_p = _agg(flat)
    con_m, con_p = _agg(contrast_frame)
    zcr_m, zcr_p = _agg(zcr)
    ons_m, ons_p = _agg(onset_env)
    rms_m, rms_p = _agg(rms)

    return {
        "duration_sec": round(dur, 2),
        "cen_mean": cen_m, "cen_p90": cen_p,
        "roll_mean": roll_m, "roll_p90": roll_p,
        "bw_mean": bw_m, "bw_p90": bw_p,
        "flat_mean": flat_m, "flat_p90": flat_p,
        "contrast_mean": con_m, "contrast_p90": con_p,
        "zcr_mean": zcr_m, "zcr_p90": zcr_p,
        "perc_mean": float(np.mean(perc)),
        "perc_p90": float(np.percentile(perc, 90)),
        "perc_p95": float(np.percentile(perc, 95)),
        "onset_mean": ons_m, "onset_p90": ons_p,
        "onset_rate": onset_rate,
        "rms_mean": rms_m, "rms_p90": rms_p,
    }


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path) → 결과 행 dict.

    실패해도 죽지 않고 error 필드를 담아 반환한다(전체 배치 진행 보장).
    """
    idx, band, song, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path))
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
            # cen_mean이 채워진(=정상) 행만 done으로 간주
            if (r.get("cen_mean") or "").strip():
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
        path = _audio_path(band, idx)
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

    ap = argparse.ArgumentParser(description="전곡 에너지 피처 추출(resumable, 병렬)")
    ap.add_argument("--workers", type=int, default=8, help="병렬 worker 수(기본 8)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not _AUDIO_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {_AUDIO_DIR}")

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
    # --idx 재추출 시에도 append(중복 idx는 build 단계에서 최신 우선 처리)
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
                print(f"  진행 {i}/{len(tasks)}  ok={n_ok} err={n_err}  "
                      f"{rate:.2f}곡/s  ETA {eta/60:.1f}분", flush=True)

        if args.workers > 1:
            pool.close()
            pool.join()
    finally:
        f.close()

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {_OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
