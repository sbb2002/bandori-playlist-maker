"""WSL2 전용: Essentia Danceability(DFA 지수) 피처 추출 스크립트.

배경 / 실행 환경
---------------
Essentia의 Danceability 알고리즘은 DFA(Detrended Fluctuation Analysis) 기반으로,
비트 규칙성이 높을수록 낮은 α값(0~...)을 가지며, 이는 음악의 댄서빌리티(춤추기 좋음)
와 연관이 있다.

⚠️ WSL2 필요: 현 Windows Python 환경엔 Essentia가 설치되지 않아, 지금은 실행 불가.
코드만 작성하며, WSL2 구축 이후 실행·검증한다.

산출물
-----
`out/danceability_raw.csv` — idx별 DFA 알파, 정규화된 댄서빌리티(0-1)
구조:
  idx, band, song, duration_sec,
  dfa_alpha,        # 원시 DFA 지수 (낮을수록 danceable)
  danceability_norm,   # 0-1 정규화(백분위 상대)
  dfa_alpha_native,    # 네이티브 참고값(선택)
  danceability_clf_prob,  # ML 분류기 참고값
  error

실행
----
    # WSL2에서만 가능:
    python src/extract_danceability_essentia.py
    python src/extract_danceability_essentia.py --limit 20
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
# 경로 설정 (CONVENTIONS.md 규약)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # method-7-danceability/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-7-danceability/
_TOPIC_DIR = _METHOD_DIR.parent                       # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                    # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                  # pyworks/

_MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
_AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)
_OUT_CSV = _METHOD_DIR / "out" / "csv" / "danceability_raw.csv"
_OUT_TIMESERIES = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# Essentia 임포트 (WSL2 전용)
# ---------------------------------------------------------------------------
_ESSENTIA_AVAILABLE = False
try:
    import essentia.standard as es
    _ESSENTIA_AVAILABLE = True
except ImportError as e:
    _ESSENTIA_MSG = (
        "\n"
        "=== Essentia 라이브러리 없음 ===\n"
        "이 스크립트는 WSL2 환경에서만 실행 가능합니다.\n"
        "Windows 네이티브 Python에서는 실행할 수 없습니다.\n"
        "\n"
        "WSL2에서 다음을 실행하십시오:\n"
        "  pip install essentia essentia-tensorflow\n"
        "  python extract_danceability_essentia.py\n"
        f"\nOriginal error: {e}\n"
    )

# ---------------------------------------------------------------------------
# 추출 파라미터
# ---------------------------------------------------------------------------
SR = 44100  # Essentia Danceability 표준 샘플링 레이트

# 출력 컬럼
FEATURE_COLUMNS = [
    "idx",
    "band",
    "song",
    "duration_sec",
    "dfa_alpha",
    "danceability_norm",
    "dfa_alpha_native",
    "danceability_clf_prob",
]

_EPS = 1e-9


def extract_features(path: Path) -> dict[str, float | str]:
    """단일 오디오 파일에서 Essentia Danceability를 추출.

    Essentia의 Danceability 알고리즘이 DFA 지수와 정규화된 댄서빌리티 확률을 반환한다.

    Returns:
        dict with keys: duration_sec, dfa_alpha, danceability_clf_prob
        (danceability_norm은 나중에 전체 표본 기준 백분위로 계산)
    """
    if not _ESSENTIA_AVAILABLE:
        raise ImportError("Essentia 라이브러리가 설치되지 않았습니다. WSL2를 사용하세요.")

    # Essentia 로더 (mono, 44100 Hz)
    audio = es.MonoLoader(filename=str(path), sampleRate=SR)()

    # Essentia Danceability
    # 실측 API: (danceability, dfa) 반환. danceability는 스칼라(0~약3, 높을수록 danceable).
    # dfa는 tau(세그먼트 길이)별 DFA 지수로 이뤄진 벡터이지 스칼라가 아니다 — 이 벡터의
    # 평균을 대표 스칼라로 사용한다(낮을수록 리듬이 규칙적 = danceable 경향).
    danceability_score, dfa_vector = es.Danceability()(audio)
    dfa_alpha = float(np.mean(dfa_vector))
    danceability_clf_prob = float(danceability_score)

    dur = float(len(audio) / SR)

    return {
        "duration_sec": round(dur, 2),
        "dfa_alpha": dfa_alpha,
        "danceability_clf_prob": danceability_clf_prob,
    }


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 worker.

    (idx, band, song, path) → 결과 행 dict.
    실패해도 죽지 않고 error 필드를 담아 반환한다.
    """
    idx, band, song, path = task
    t0 = time.time()
    try:
        feats = extract_features(Path(path))
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "error": "",
            "danceability_norm": "",  # 나중에 백분위로 채움
            "dfa_alpha_native": "",   # 네이티브 버전 없음
            **feats,
        }
    except Exception as exc:
        return {
            "idx": idx,
            "band": band,
            "song": song,
            "error": repr(exc),
            "duration_sec": "",
            "dfa_alpha": "",
            "danceability_norm": "",
            "dfa_alpha_native": "",
            "danceability_clf_prob": "",
        }


def _load_master() -> list[dict[str, str]]:
    """songs_master.csv 로드."""
    with _MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _done_idxs() -> set[int]:
    """이미 추출 완료된 idx 읽기 (resume)."""
    if not _OUT_CSV.exists():
        return set()
    done: set[int] = set()
    with _OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("dfa_alpha") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _audio_path(band: str, idx: int) -> Path:
    """오디오 파일 경로."""
    return _AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _build_tasks(
    rows: list[dict[str, str]],
    done: set[int],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str, str]]:
    """처리할 태스크 목록 작성."""
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
    """CSV 라이터 열기."""
    header_needed = not (_OUT_CSV.exists() and _OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    f = _OUT_CSV.open(mode, encoding="utf-8", newline="")
    cols = FEATURE_COLUMNS + ["error"]
    writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def _compute_percentile_norm(rows: list[dict]) -> dict[int, float]:
    """
    전체 표본의 dfa_alpha 기준으로 백분위 정규화를 계산.

    danceability_norm = 1 - percentile_rank(dfa_alpha)
    (낮은 α = 높은 댄서빌리티 = 1에 가까움)

    returns: dict[idx, danceability_norm]

    ⚠️ 주석: 현재 661곡 파일럿 표본 내부 기준으로 계산.
    전수 확장 시 다시 계산 필요.
    """
    valid_rows = []
    for r in rows:
        alpha_val = r.get("dfa_alpha")
        # 숫자이고 error가 없으면 유효
        if alpha_val != "" and r.get("error") == "":
            try:
                float(alpha_val)
                valid_rows.append(r)
            except (ValueError, TypeError):
                continue

    if not valid_rows:
        return {}

    alphas = [float(r["dfa_alpha"]) for r in valid_rows]
    alphas_arr = np.array(alphas)

    norms: dict[int, float] = {}
    for r in valid_rows:
        alpha = float(r["dfa_alpha"])
        # percentile_rank: 같거나 작은 값의 비율
        percentile = (alphas_arr <= alpha).sum() / len(alphas_arr)
        # 역순: 낮은 α = 높은 댄서빌리티
        norm = 1.0 - percentile
        norms[int(r["idx"])] = round(norm, 4)

    return norms


def main() -> None:
    """메인 실행."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    # Essentia 확인
    if not _ESSENTIA_AVAILABLE:
        print(_ESSENTIA_MSG, file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(
        description="Essentia Danceability(DFA) 피처 추출 (WSL2 필수, resumable, 병렬)"
    )
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not _AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {_AUDIO_FULL_DIR}")

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

        results = []
        for i, res in enumerate(it, 1):
            results.append(res)
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

        # 백분위 정규화 계산 후 CSV에 기입
        norms = _compute_percentile_norm(results)
        for res in results:
            if res.get("error") == "" and int(res["idx"]) in norms:
                res["danceability_norm"] = norms[int(res["idx"])]
            writer.writerow(res)
        f.flush()

    finally:
        f.close()

    print(
        f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분",
        flush=True,
    )
    print(f"산출: {_OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
