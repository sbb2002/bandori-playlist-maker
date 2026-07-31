"""보컬 스템 에너지비 기반 instrumentalness 피처 추출 스크립트 (네이티브).

배경 / 개념
-----------
Bandori 카탈로그 중 30곡(6밴드×5곡)에 대해 htdemucs 보컬 분리 모델로 얻은
`vocals.wav`와 `no_vocals.wav` 스템을 이용해, 보컬 에너지 비중을 직접 측정한다:
    instr_stem_ratio = 1 - vocal_energy / total_energy

이는 instrumentalness(악기 중심도)의 대체 지표로 사용될 수 있으며, Essentia의
딥러닝 기반 voice_instrumental 분류기와 비교·검증할 수 있다.

산출물
------
`out/instrumentalness_raw.csv` — idx별 원시 피처:
  - idx, band, song, duration_sec: 기본 정보
  - instr_stem_ratio: 1 - vocal_energy/total_energy (0~1)
  - voice_median, voice_p10, voice_p90, voice_std: Essentia 컬럼(스템 버전은 공백)
  - n_patches: (스템 버전은 공백)
  - error: "no_stem" / "" 등

주의
----
- 스템은 661곡 중 30곡만 존재 → 나머지는 error="no_stem"으로 기록(스크립트 안전 종료).
- 오디오/스템 파일은 저작물 → **읽기 전용**. 커밋/이동/삭제 금지.

실행
----
    python src/extract_instrumentalness_stem.py               # 전곡, 병렬(기본 4 worker)
    python src/extract_instrumentalness_stem.py --workers 8
    python src/extract_instrumentalness_stem.py --limit 10    # 앞 10곡만(테스트)
    python src/extract_instrumentalness_stem.py --idx 0,1,2   # 특정 idx만
    python src/extract_instrumentalness_stem.py --fresh       # 기존 출력 무시
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
# 경로
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent  # method-9-*/src/
_METHOD_DIR = _THIS_DIR.parent  # method-9-*/
_TOPIC_DIR = _METHOD_DIR.parent  # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]  # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent  # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-playlist-maker"
    / "topic"
    / "mfcc_analysis"
    / "stems"
    / "htdemucs"
)

OUT_CSV = _METHOD_DIR / "out" / "instrumentalness_raw.csv"
TIMESERIES_DIR = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# 추출 파라미터 (재현성 고정)
# ---------------------------------------------------------------------------
SR = 22050

# 출력 컬럼 (순서 고정)
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "instr_stem_ratio",
    "voice_median",
    "voice_p10",
    "voice_p90",
    "voice_std",
    "n_patches",
]


def stem_paths(band: str, idx: int) -> tuple[Path, Path] | None:
    """스템 폴더 검사. 존재하면 (vocals.wav, no_vocals.wav) 경로 튜플 반환, 없으면 None."""
    stem_dir = VOCAL_STEM_DIR / f"{band}__{idx:03d}"
    if not stem_dir.is_dir():
        return None
    vocal_path = stem_dir / "vocals.wav"
    instr_path = stem_dir / "no_vocals.wav"
    if not (vocal_path.exists() and instr_path.exists()):
        return None
    return vocal_path, instr_path


def extract_features(band: str, idx: int) -> dict[str, float]:
    """단일 곡의 보컬 스템 에너지비를 계산해 dict로 반환.

    반환 값:
      - instr_stem_ratio: 1 - vocal_energy / (vocal_energy + instr_energy)
      - duration_sec: 오디오 길이(초)
      또는 error 필드가 채워짐.
    """
    import librosa  # worker 프로세스에서 import (spawn 안전)

    paths = stem_paths(band, idx)
    if paths is None:
        return {"error": "no_stem"}

    vocal_path, instr_path = paths

    try:
        # 보컬 스템 로드
        y_vocal, sr = librosa.load(str(vocal_path), sr=SR, mono=True)
        dur = float(len(y_vocal) / sr)

        # 악기(non-vocal) 스템 로드
        y_instr, _ = librosa.load(str(instr_path), sr=SR, mono=True)

        # 에너지 계산 (RMS에 비례하는 전력의 합)
        vocal_energy = float(np.sum(y_vocal ** 2))
        instr_energy = float(np.sum(y_instr ** 2))
        total_energy = vocal_energy + instr_energy

        # 악기 비율: 1 - (보컬에너지 / 전체에너지)
        if total_energy > 0:
            instr_ratio = 1.0 - (vocal_energy / total_energy)
        else:
            instr_ratio = 0.0

        return {
            "duration_sec": round(dur, 2),
            "instr_stem_ratio": round(instr_ratio, 6),
        }

    except Exception as exc:
        return {"error": repr(exc)}


def _worker(task: tuple[int, str, str]) -> dict:
    """멀티프로세싱 worker. (idx, band, song) → 결과 행 dict.

    실패해도 죽지 않고 error 필드를 담아 반환한다.
    """
    idx, band, song = task
    try:
        feats = extract_features(band, idx)
        if "error" in feats:
            return {"idx": idx, "band": band, "song": song, "error": feats["error"]}
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": feats.get("duration_sec", ""),
            "instr_stem_ratio": feats.get("instr_stem_ratio", ""),
            "voice_median": "",
            "voice_p10": "",
            "voice_p90": "",
            "voice_std": "",
            "n_patches": "",
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


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx를 읽어 resume 근거로 삼는다."""
    if not OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # instr_stem_ratio가 채워진(=정상) 행만 done으로 간주
            if (r.get("instr_stem_ratio") or "").strip():
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
) -> list[tuple[int, str, str]]:
    """처리할 곡 태스크 생성. 스템 폴더 존재 여부로 필터링."""
    tasks: list[tuple[int, str, str]] = []
    skipped_no_stem = 0
    for r in rows:
        idx = int(r["idx"])
        if only_idx is not None and idx not in only_idx:
            continue
        if only_idx is None and idx in done:
            continue
        band = r["band"]

        # 스템 폴더 존재 확인
        if stem_paths(band, idx) is None:
            skipped_no_stem += 1
            continue

        tasks.append((idx, band, r["song"]))
        if limit is not None and len(tasks) >= limit:
            break

    if skipped_no_stem > 0:
        print(
            f"  [스킵] 스템 없음 {skipped_no_stem}곡 (전체 {len(rows)}곡 중 스템 {len(tasks)}곡)",
            flush=True,
        )

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

    ap = argparse.ArgumentParser(description="보컬 스템 에너지비 기반 instrumentalness 추출")
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not MASTER_CSV.exists():
        raise FileNotFoundError(f"songs_master.csv 없음: {MASTER_CSV}")

    if not VOCAL_STEM_DIR.exists():
        print(f"[경고] 스템 디렉터리 없음: {VOCAL_STEM_DIR}", flush=True)

    rows = _load_master()
    only_idx = (
        {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    )
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit)

    print(
        f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, "
        f"이번 처리(스템 있음) {len(tasks)}곡, "
        f"worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료 또는 스템 없음).", flush=True)
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
                # 정상 결과 샘플 출력
                ratio = res.get("instr_stem_ratio", "")
                if i % 5 == 0 or i == len(tasks):
                    print(
                        f"  idx={res['idx']:3d} instr_ratio={ratio:.4f} "
                        f"dur={res.get('duration_sec', '')}s",
                        flush=True,
                    )

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
