"""조성(key) 추출: Krumhansl-Kessler 템플릿 기반 분석.

배경 / 개념
-----------
리듬게임 곡의 조성을 저자동으로 판정한다. Krumhansl-Kessler(1982) 24개 템플릿
(major 12키 + minor 12키)을 크로마 벡터에 매칭해 윈도우별 키를 추정하고,
지속시간 가중 다수결로 전곡 대표 키를 결정한다.

전곡 단일 평균 크로마는 후렴 전조 등으로 인해 두 키의 혼합이 되므로 사용하지 않음.
대신 10~20초 윈도우별로 분석해 구간별 안정성을 확보한다.

산출물
------
- `out/key_raw.csv` — idx별 최종 키/모드 + 신뢰도 지표
- `out/timeseries/<idx>_key_windows.csv` — 윈도우별 원시 결과(재집계용)

실행
----
    python src/extract_key_ks.py               # 전곡, 병렬(기본 8 worker)
    python src/extract_key_ks.py --workers 4
    python src/extract_key_ks.py --limit 5     # 앞 5곡만(테스트)
    python src/extract_key_ks.py --window-sec 10  # 윈도우 10초

중단해도 안전: 이미 `key_raw.csv`에 있는 idx는 건너뛴다(resume).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr

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

OUT_DIR = _METHOD_DIR / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = OUT_DIR / "key_raw.csv"
TIMESERIES_DIR = OUT_DIR / "timeseries"
TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Krumhansl-Kessler 템플릿 (24개)
# ---------------------------------------------------------------------------
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# 음이름 (C, C#, D, D#, E, F, F#, G, G#, A, A#, B)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 추출 파라미터 (재현성)
SR = 22050
N_FFT = 2048
HOP = 512
WINDOW_SEC = 15.0  # 기본 15초, CLI로 조정 가능
MODULATION_THRESHOLD = 0.25  # 2위 후보가 전체의 25% 이상이면 전조 플래그

# 출력 컬럼
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "key_ks",
    "mode_ks",
    "key_ks_confidence",
    "modulation_flag",
    "key_essentia",
    "mode_essentia",
    "key_mismatch",
    "mode_only_mismatch",
    "error",
]


def _rotate_profile(profile: list[float], shift: int) -> list[float]:
    """프로필을 shift칸 회전(12음 음 중심)."""
    return [profile[(i - shift) % 12] for i in range(12)]


def _build_templates() -> dict[str, tuple[str, list[float]]]:
    """24개 템플릿(major 12 + minor 12) 생성.

    반환: {key_name -> (mode, profile_list)}
    예: {"C_major" -> ("major", [6.35, ...])}
    """
    templates = {}
    for shift in range(12):
        key = NOTE_NAMES[shift]
        major_prof = _rotate_profile(MAJOR_PROFILE, shift)
        minor_prof = _rotate_profile(MINOR_PROFILE, shift)
        templates[f"{key}_major"] = ("major", major_prof)
        templates[f"{key}_minor"] = ("minor", minor_prof)
    return templates


def _chroma_to_template_match(chroma: np.ndarray, templates: dict) -> tuple[str, str, float]:
    """12음 크로마 벡터(평균)를 24개 템플릿과 매칭.

    반환: (key_str, mode_str, correlation)
    """
    chroma = chroma / (np.linalg.norm(chroma) + 1e-9)  # 정규화

    best_corr = -2.0
    best_key = None
    best_mode = None

    for template_name, (mode, profile) in templates.items():
        # 정규화된 프로필
        profile_norm = np.array(profile) / (np.linalg.norm(profile) + 1e-9)
        corr, _ = pearsonr(chroma, profile_norm)
        if corr > best_corr:
            best_corr = corr
            best_key, _ = template_name.split("_")
            best_mode = mode

    return best_key, best_mode, float(best_corr)


def _sliding_window_keys(
    path: Path, window_sec: float = WINDOW_SEC
) -> tuple[list[dict], float]:
    """슬라이딩 윈도우로 크로마 추출 및 키 매칭.

    반환: ([{window_start_sec, window_end_sec, key, mode, corr}, ...], duration_sec)
    """
    import librosa

    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)

    # CQT 크로마 (librosa 기본 C1 기준)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)  # (12, frames)
    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=HOP)

    # 윈도우 샘플 횟수
    window_frames = int(window_sec * sr / HOP)

    templates = _build_templates()
    windows = []

    # 겹치는 윈도우: 50% 스트라이드(안정성 확보)
    stride_frames = window_frames // 2
    for start_frame in range(0, chroma.shape[1], stride_frames):
        end_frame = min(start_frame + window_frames, chroma.shape[1])
        if end_frame - start_frame < window_frames // 2:  # 너무 짧은 윈도우 제외
            continue

        # 윈도우 크로마 평균
        chroma_win = chroma[:, start_frame:end_frame].mean(axis=1)

        # 템플릿 매칭
        key, mode, corr = _chroma_to_template_match(chroma_win, templates)

        start_sec = float(frame_times[start_frame])
        end_sec = float(frame_times[end_frame - 1])

        windows.append(
            {
                "window_start_sec": round(start_sec, 2),
                "window_end_sec": round(end_sec, 2),
                "key": key,
                "mode": mode,
                "corr": round(corr, 4),
            }
        )

    return windows, dur


def _majority_vote(windows: list[dict], modulation_threshold: float = 0.25) -> dict:
    """윈도우별 키를 지속시간 가중 다수결로 집계.

    반환: {key, mode, confidence, modulation_flag}
    """
    if not windows:
        return {
            "key_ks": None,
            "mode_ks": None,
            "key_ks_confidence": None,
            "modulation_flag": False,
        }

    # 키별 누적 지속시간 계산
    key_mode_duration = {}  # {(key, mode) -> duration}
    for w in windows:
        dur = w["window_end_sec"] - w["window_start_sec"]
        key_mode = (w["key"], w["mode"])
        key_mode_duration[key_mode] = key_mode_duration.get(key_mode, 0) + dur

    # 정렬: 지속시간 내림차순
    sorted_items = sorted(key_mode_duration.items(), key=lambda x: x[1], reverse=True)

    if not sorted_items:
        return {
            "key_ks": None,
            "mode_ks": None,
            "key_ks_confidence": None,
            "modulation_flag": False,
        }

    (best_key, best_mode), best_dur = sorted_items[0]
    total_dur = sum(d for _, d in sorted_items)
    confidence = best_dur / total_dur if total_dur > 0 else 0.0

    # 전조 플래그: 2위 후보 지속시간이 전체의 threshold 이상
    modulation = False
    if len(sorted_items) > 1:
        second_dur = sorted_items[1][1]
        modulation = (second_dur / total_dur) >= modulation_threshold

    return {
        "key_ks": best_key,
        "mode_ks": best_mode,
        "key_ks_confidence": round(confidence, 3),
        "modulation_flag": modulation,
    }


def extract_features(path: Path, window_sec: float = WINDOW_SEC) -> dict[str, str | float]:
    """단일 오디오 파일에서 키 피처 추출.

    반환: {key_ks, mode_ks, key_ks_confidence, modulation_flag, window_windows_data}
    """
    windows, dur = _sliding_window_keys(path, window_sec=window_sec)
    agg = _majority_vote(windows, modulation_threshold=MODULATION_THRESHOLD)

    return {
        "duration_sec": round(dur, 2),
        "key_ks": agg["key_ks"],
        "mode_ks": agg["mode_ks"],
        "key_ks_confidence": agg["key_ks_confidence"],
        "modulation_flag": agg["modulation_flag"],
        "windows": windows,  # 별도로 저장할 데이터
    }


def _worker(task: tuple[int, str, str, str, float]) -> dict:
    """멀티프로세싱 워커. (idx, band, song, path, window_sec) → 결과 행.

    실패해도 죽지 않고 error 필드를 담아 반환한다.
    """
    idx, band, song, path, window_sec = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path), window_sec=window_sec)
        windows = feats.pop("windows")  # 별도 처리

        # 윈도우 결과 저장
        _save_windows_csv(idx, windows)

        return {
            "idx": idx,
            "band": band,
            "song": song,
            "key_essentia": "",  # 빈칸(essentia 스크립트가 채움)
            "mode_essentia": "",
            "key_mismatch": "",
            "mode_only_mismatch": "",
            "error": "",
            **feats,
        }
    except Exception as exc:
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "duration_sec": "",
            "key_ks": "",
            "mode_ks": "",
            "key_ks_confidence": "",
            "modulation_flag": "",
            "key_essentia": "",
            "mode_essentia": "",
            "key_mismatch": "",
            "mode_only_mismatch": "",
            "error": repr(exc),
        }


def _save_windows_csv(idx: int, windows: list[dict]) -> None:
    """윈도우별 원시 결과를 CSV로 저장."""
    csv_path = TIMESERIES_DIR / f"{idx}_key_windows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        if windows:
            writer = csv.DictWriter(
                f, fieldnames=["window_start_sec", "window_end_sec", "key", "mode", "corr"]
            )
            writer.writeheader()
            writer.writerows(windows)


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
            # key_ks가 채워진 행만 done으로 간주
            if (r.get("key_ks") or "").strip():
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
    window_sec: float,
) -> list[tuple[int, str, str, str, float]]:
    """처리 대상 곡 리스트 생성."""
    tasks: list[tuple[int, str, str, str, float]] = []
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
        tasks.append((idx, band, r["song"], str(path), window_sec))
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def _open_writer(append: bool):
    """CSV 라이터 오픈."""
    header_needed = not (OUT_CSV.exists() and OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = OUT_CSV.open(mode, encoding="utf-8", newline="")
    writer = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description="조성(key) 추출: Krumhansl-Kessler 템플릿")
    ap.add_argument("--workers", type=int, default=8, help="병렬 worker 수(기본 8)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    ap.add_argument(
        "--window-sec",
        type=float,
        default=WINDOW_SEC,
        help=f"윈도우 길이(초, 기본 {WINDOW_SEC})",
    )
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    rows = _load_master()
    only_idx = {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    done = set() if (args.fresh or only_idx is not None) else _done_idxs()
    tasks = _build_tasks(rows, done, only_idx, args.limit, args.window_sec)

    print(
        f"전체 {len(rows)}곡, 이미완료 {len(done)}곡, 이번 처리 {len(tasks)}곡, "
        f"worker={args.workers}, window={args.window_sec}초",
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

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {OUT_CSV}", flush=True)
    print(f"윈도우 원시: {TIMESERIES_DIR}", flush=True)


if __name__ == "__main__":
    main()
