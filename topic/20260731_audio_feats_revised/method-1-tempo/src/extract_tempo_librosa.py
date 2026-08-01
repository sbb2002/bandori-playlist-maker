"""1차 tempo 후보 추출 스크립트 (librosa 자기상관 기반).

배경 / 문제
-----------
Bandori 661곡의 BPM(Beats Per Minute)을 추출한다. librosa의 자기상관 기반 tempo 추정을
1차 후보로 사용하고, madmom DBNBeatTracker는 별도 스크립트에서 정제값으로 제공한다.

무엇을 뽑는가
-------------
- bpm_autocorr: librosa.beat.tempo()의 자기상관 피크 (단일 스칼라, BPM)
- duration_sec: 곡 길이(초)

산출물
------
`out/tempo_raw.csv` — idx별 원시 BPM 값 (증분 append, resume 가능).
이 스크립트는 **bpm_autocorr 컬럼만** 채운다. madmom 스크립트가 bpm_madmom/beat_count/
beat_interval_median_sec/halftime_flag를 추가한다.

주의
----
- 오디오 파일은 저작물 → **읽기 전용**. 커밋/이동/삭제 금지.
- 쓰기 대상: `out/tempo_raw.csv` 뿐.

실행
----
    python src/extract_tempo_librosa.py               # 전곡, 병렬(기본 8 worker)
    python src/extract_tempo_librosa.py --workers 10
    python src/extract_tempo_librosa.py --limit 20    # 앞 20곡만(테스트)
    python src/extract_tempo_librosa.py --idx 278,272,512  # 특정 idx만

중단해도 안전: 이미 `out/tempo_raw.csv`에 있는 idx는 건너뛴다(resume).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")  # librosa deprecation·UserWarning 소음 제거

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # method-1-tempo/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-1-tempo/
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
_OUT_CSV = _METHOD_DIR / "out" / "csv" / "tempo_raw.csv"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 22050

# 출력 컬럼 (순서 고정 → 재현/병합 안정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "bpm_autocorr",
]


def extract_features(path: Path) -> dict[str, float]:
    """단일 오디오 파일에서 librosa 자기상관 기반 tempo를 뽑아 dict로 반환.

    librosa.beat.tempo()의 자기상관 피크를 bpm_autocorr로 사용한다.
    """
    import librosa  # worker 프로세스에서 import (spawn 안전)

    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)

    # onset_strength (spectral flux) 계산
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # 자기상관 기반 tempo 후보 (aggregate=None으로 최빈값 대신 전체 배열)
    tempo_candidates = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)

    # 최빈값 (가장 신뢰도 높은 피크)
    if tempo_candidates is not None and len(tempo_candidates) > 0:
        bpm = float(tempo_candidates[0])  # 첫 번째 피크가 최빈값
    else:
        bpm = np.nan

    return {
        "duration_sec": round(dur, 2),
        "bpm_autocorr": bpm,
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
            # bpm_autocorr이 채워진(=정상) 행만 done으로 간주
            if (r.get("bpm_autocorr") or "").strip():
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

    ap = argparse.ArgumentParser(description="librosa 자기상관 기반 tempo 추출(resumable, 병렬)")
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
