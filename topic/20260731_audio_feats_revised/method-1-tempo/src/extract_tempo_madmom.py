"""정제 tempo 후보 추출 스크립트 (madmom DBNBeatTracker 기반, WSL2 전용).

배경 / 문제
-----------
librosa의 자기상관 기반 tempo를 1차 후보로 사용하되, madmom의 DBNBeatTracker는
신경망 기반 비트 추정으로 더 정확한 정제값(bpm_madmom)을 제공한다.

IMPORTANT: 이 스크립트는 **WSL2 환경에서만 실행 가능**하다. 현재 Windows 환경에는
madmom이 설치돼 있지 않으므로, 이 스크립트는 import 시점에 실패할 것이다.
WSL2 구축 이후 실행한다.

무엇을 뽑는가
-------------
- bpm_madmom: DBNBeatTracker 기반 정제 BPM (단일 스칼라)
- beat_count: 추정된 비트 개수
- beat_interval_median_sec: 비트 간격의 중앙값(초)
- halftime_flag: 비트 간격 불안정성 플래그 (IQR/median > 0.3)

산출물
------
`out/tempo_raw.csv` — idx별 원시 BPM 값 (증분 append, resume 가능).
이 스크립트는 **bpm_madmom/beat_count/beat_interval_median_sec/halftime_flag 컬럼을
채운다**. librosa 스크립트가 먼저 bpm_autocorr를 채운다(또는 --idx로 특정 곡만 재처리).

주의
----
- 오디오 파일은 저작물 → **읽기 전용**. 커밋/이동/삭제 금지.
- 쓰기 대상: `out/tempo_raw.csv` 뿐.

실행 (WSL2 필요)
----------------
    # WSL2 쉘에서:
    python src/extract_tempo_madmom.py               # 전곡, 병렬(기본 4 worker, 모델 로딩 비용)
    python src/extract_tempo_madmom.py --workers 2
    python src/extract_tempo_madmom.py --limit 20    # 앞 20곡만(테스트)
    python src/extract_tempo_madmom.py --idx 278,272,512  # 특정 idx만
    python src/extract_tempo_madmom.py --min-bpm 55 --max-bpm 320  # BPM 범위 커스터마이즈

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

warnings.filterwarnings("ignore")  # librosa/madmom deprecation·UserWarning 소음 제거

# ---------------------------------------------------------------------------
# madmom 가용성 확인
# ---------------------------------------------------------------------------
try:
    from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
except ImportError as e:
    print("=" * 70, file=sys.stderr)
    print("오류: madmom 라이브러리가 설치돼 있지 않습니다.", file=sys.stderr)
    print("", file=sys.stderr)
    print("이 스크립트는 WSL2 환경에서만 실행 가능합니다.", file=sys.stderr)
    print("현재 환경은 Windows Python이므로 madmom을 설치할 수 없습니다.", file=sys.stderr)
    print("", file=sys.stderr)
    print("다음 단계를 따르세요:", file=sys.stderr)
    print("  1. WSL2 Linux 쉘을 열기", file=sys.stderr)
    print("  2. pip install madmom (또는 GitHub master에서 빌드)", file=sys.stderr)
    print("  3. WSL2 쉘에서 이 스크립트 실행", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"원래 오류: {e}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    sys.exit(1)

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
_OUT_CSV = _METHOD_DIR / "out" / "tempo_raw.csv"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 22050
DEFAULT_MIN_BPM = 55
DEFAULT_MAX_BPM = 320
HALFTIME_THRESHOLD = 0.3  # IQR/median > 이 값이면 halftime_flag=True

# 출력 컬럼 (순서 고정 → 재현/병합 안정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "bpm_madmom",
    "beat_count",
    "beat_interval_median_sec",
    "halftime_flag",
]


def extract_features(path: Path, min_bpm: int = DEFAULT_MIN_BPM, max_bpm: int = DEFAULT_MAX_BPM) -> dict[str, float | int | bool]:
    """단일 오디오 파일에서 madmom DBNBeatTracker 기반 tempo를 뽑아 dict로 반환.

    RNNBeatProcessor로 비트 활성도(activation)를 계산하고,
    DBNBeatTrackingProcessor로 비트 타임스탬프를 추정한다.
    """
    y_path = str(path)

    # RNNBeatProcessor: 비트 활성도 계산
    rnn = RNNBeatProcessor()
    act = rnn(y_path)

    # DBNBeatTrackingProcessor: 동적 계획법으로 최적 비트 시퀀스 추정
    proc = DBNBeatTrackingProcessor(min_bpm=min_bpm, max_bpm=max_bpm, fps=100)
    beats = proc(act)  # 초 단위 비트 타임스탬프 배열 (numpy array)

    beat_count = len(beats)
    if beat_count < 2:
        # 비트를 충분히 찾지 못한 경우
        return {
            "duration_sec": 0.0,
            "bpm_madmom": np.nan,
            "beat_count": beat_count,
            "beat_interval_median_sec": np.nan,
            "halftime_flag": False,
        }

    # 비트 간격 계산
    intervals = np.diff(beats)  # 연속 비트 사이 간격(초)

    # 중앙값 기반 BPM 계산 (60 = 1분)
    interval_median = float(np.median(intervals))
    bpm_madmom = 60.0 / interval_median if interval_median > 0 else np.nan

    # halftime_flag: 비트 간격 불안정성 검사
    # 사분위 범위(IQR) / 중앙값이 임계값 초과 시 비트 간격이 불안정함을 의미
    q25 = float(np.percentile(intervals, 25))
    q75 = float(np.percentile(intervals, 75))
    iqr = q75 - q25
    halftime_flag = bool(iqr / interval_median > HALFTIME_THRESHOLD) if interval_median > 0 else False

    duration_sec = float(beats[-1]) if len(beats) > 0 else 0.0

    return {
        "duration_sec": round(duration_sec, 2),
        "bpm_madmom": bpm_madmom,
        "beat_count": beat_count,
        "beat_interval_median_sec": round(interval_median, 4),
        "halftime_flag": halftime_flag,
    }


def _worker(task: tuple[int, str, str, str, int, int]) -> dict:
    """멀티프로세싱 worker. (idx, band, song, path, min_bpm, max_bpm) → 결과 행 dict.

    실패해도 죽지 않고 error 필드를 담아 반환한다(전체 배치 진행 보장).
    """
    idx, band, song, path, min_bpm, max_bpm = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path), min_bpm=min_bpm, max_bpm=max_bpm)
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
            # bpm_madmom이 채워진(=정상) 행만 done으로 간주
            if (r.get("bpm_madmom") or "").strip():
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
    min_bpm: int,
    max_bpm: int,
) -> list[tuple[int, str, str, str, int, int]]:
    tasks: list[tuple[int, str, str, str, int, int]] = []
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
        tasks.append((idx, band, r["song"], str(path), min_bpm, max_bpm))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _merge_madmom_results(csv_path: Path, madmom_results: dict[int, dict]) -> None:
    """기존 tempo_raw.csv(librosa가 만든 bpm_autocorr 등)에 madmom 컬럼을 idx 기준으로
    병합한다 — 덮어쓰기가 아니라 컬럼만 채움(SPEC.md "같은 CSV를 다른 컬럼 세트로 채운다"
    요건). 파일이 아직 없으면(= librosa 스크립트를 먼저 안 돌렸으면) madmom 컬럼만 있는
    새 CSV를 만든다."""
    madmom_cols = ["bpm_madmom", "beat_count", "beat_interval_median_sec", "halftime_flag"]

    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = []

    existing_idx = {int(r["idx"]) for r in rows}
    for idx, res in madmom_results.items():
        row_update = {
            "duration_sec": res.get("duration_sec", ""),
            "bpm_madmom": res.get("bpm_madmom", ""),
            "beat_count": res.get("beat_count", ""),
            "beat_interval_median_sec": res.get("beat_interval_median_sec", ""),
            "halftime_flag": res.get("halftime_flag", ""),
            "extract_sec": res.get("extract_sec", ""),
            "error": res.get("error", ""),
        }
        if idx in existing_idx:
            for r in rows:
                if int(r["idx"]) == idx:
                    # duration_sec은 librosa가 이미 채웠으면 madmom 값(빈 값 포함)으로 덮지
                    # 않는다(madmom 실패로 librosa 값이 지워지는 사고 방지). error는 이번 실행
                    # 결과가 이 idx에 대한 최신 진실이므로 항상 덮어써서 이전 실패 잔여물이
                    # 성공 후에도 남지 않게 한다.
                    for k, v in row_update.items():
                        if k == "duration_sec" and (r.get(k) or "").strip() and not str(v).strip():
                            continue
                        r[k] = v
                    break
        else:
            new_row = {"idx": idx, "band": res.get("band", ""), "song": res.get("song", "")}
            new_row.update(row_update)
            rows.append(new_row)
            existing_idx.add(idx)

    all_cols: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in all_cols:
                all_cols.append(k)
    for c in ["idx", "band", "song", "duration_sec", "bpm_autocorr"] + madmom_cols + ["extract_sec", "error"]:
        if c not in all_cols:
            all_cols.append(c)

    rows.sort(key=lambda r: int(r["idx"]))
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, restval="")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description="madmom DBNBeatTracker 기반 tempo 추출(resumable, 병렬, WSL2 전용)")
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4, 모델 로딩 비용으로 낮음)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    ap.add_argument("--min-bpm", type=int, default=DEFAULT_MIN_BPM, help=f"최소 BPM(기본 {DEFAULT_MIN_BPM})")
    ap.add_argument("--max-bpm", type=int, default=DEFAULT_MAX_BPM, help=f"최대 BPM(기본 {DEFAULT_MAX_BPM})")
    args = ap.parse_args()

    if not _AUDIO_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {_AUDIO_DIR}")

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit, args.min_bpm, args.max_bpm)

    print(f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, 이번 처리 {len(tasks)}곡, "
          f"worker={args.workers}, BPM 범위={args.min_bpm}~{args.max_bpm}", flush=True)
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    n_ok = n_err = 0
    madmom_results: dict[int, dict] = {}
    t_start = time.time()
    if args.workers <= 1:
        it = (_worker(t) for t in tasks)
    else:
        import multiprocessing as mp

        pool = mp.Pool(processes=args.workers)
        it = pool.imap_unordered(_worker, tasks)

    for i, res in enumerate(it, 1):
        madmom_results[res["idx"]] = res
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

    print("결과 병합 중(idx 기준, bpm_autocorr 등 기존 컬럼 보존)...", flush=True)
    _merge_madmom_results(_OUT_CSV, madmom_results)

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {_OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
