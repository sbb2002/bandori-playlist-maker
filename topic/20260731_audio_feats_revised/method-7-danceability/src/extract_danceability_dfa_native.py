"""네이티브 DFA 구현: RMS 에너지 기반 댄서빌리티 (네이티브 추출, Essentia 참고용).

배경 / 실행 환경
---------------
DFA(Detrended Fluctuation Analysis)는 시계열 신호의 장기 상관 특성을 분석하는 공개된
통계 기법이다. Essentia는 이를 오디오 신호에 직접 적용하지만, 원리 자체는 특정 라이브러리에
의존하지 않는다.

이 스크립트는 librosa로 추출한 RMS 에너지 시계열에 DFA를 적용하여 알파값을 계산한다.
- nolds 패키지가 설치되면 그것을 사용(정확, 검증됨)
- 없으면 numpy로 직접 DFA 알고리즘을 구현(fallback)

이는 Essentia 버전과 비교·교차검증 목적이며, **이 네이티브 버전이 최종 채택은 아니다**
(DESIGN.md에서 Essentia 1차 채택 명시).

산출물
------
`out/danceability_raw.csv` — idx별 DFA 알파(네이티브), 정규화된 댄서빌리티
구조는 essentia 버전과 동일하되, dfa_alpha_native는 이 버전이 산출, dfa_alpha는 빈칸.

실행
----
    # Windows 네이티브:
    python src/extract_danceability_dfa_native.py
    python src/extract_danceability_dfa_native.py --limit 5  # 테스트
    python src/extract_danceability_dfa_native.py --limit 5 --workers 1  # 단일 프로세스
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

warnings.filterwarnings("ignore")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass

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
_OUT_CSV = _METHOD_DIR / "out" / "danceability_raw.csv"
_OUT_TIMESERIES = _METHOD_DIR / "out" / "timeseries"

# ---------------------------------------------------------------------------
# nolds 임포트 시도
# ---------------------------------------------------------------------------
_NOLDS_AVAILABLE = False
try:
    from nolds import dfa as nolds_dfa
    _NOLDS_AVAILABLE = True
    _DFA_SOURCE = "nolds"
except ImportError:
    _DFA_SOURCE = "numpy (custom)"
    print(
        "⚠️ nolds 패키지가 없습니다. numpy로 DFA를 직접 구현합니다.",
        "정확도: nolds ≥ numpy 구현 (nolds 권장, 없으면 기본 구현 사용)",
        sep="\n",
        flush=True,
    )

# ---------------------------------------------------------------------------
# 추출 파라미터
# ---------------------------------------------------------------------------
SR = 22050  # librosa 표준 샘플링 레이트

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


# ---------------------------------------------------------------------------
# DFA 구현 (nolds 없을 때 fallback)
# ---------------------------------------------------------------------------


def _dfa_numpy(signal: np.ndarray, min_scale: int = 10, max_scale: int | None = None) -> float:
    """
    numpy 기반 DFA(Detrended Fluctuation Analysis) 구현.

    신호의 장기 상관 지수(Hurst 유사)를 계산.

    Args:
        signal: 1D 시계열 (예: RMS 에너지)
        min_scale: 최소 윈도우 크기 (프레임)
        max_scale: 최대 윈도우 크기 (None=len(signal)//2)

    Returns:
        float: DFA 알파값 (0.5~2.5, 낮을수록 비트 규칙성 높음 → danceable)

    알고리즘:
    1. 신호 통합(누적합)
    2. 다양한 윈도우 크기에 대해 트렌드 제거 후 변동 계산
    3. 로그-로그 회귀: log(변동) ~ log(윈도우 크기)
    4. 기울기 = 알파값
    """
    if len(signal) < 4:
        return 1.0  # 신호가 너무 짧으면 기본값

    # 1. 누적합 (integrated series)
    integrated = np.cumsum(signal - np.mean(signal))

    if max_scale is None:
        max_scale = len(integrated) // 2

    scales = np.logspace(np.log10(min_scale), np.log10(max_scale), num=20, dtype=int)
    scales = np.unique(scales)  # 중복 제거

    fluctuations = []

    for scale in scales:
        # 신호를 scale 크기의 청크로 나누기
        n_chunks = len(integrated) // scale
        if n_chunks < 1:
            continue

        # 포워드·역방향 피팅 (표준 DFA 절차)
        fluctuation = 0.0

        # 포워드: 시작부터 n_chunks*scale까지
        for i in range(n_chunks):
            start = i * scale
            end = start + scale
            chunk = integrated[start:end]
            x = np.arange(len(chunk))
            # 1차 다항식(선형) 피팅
            coeffs = np.polyfit(x, chunk, 1)
            trend = np.polyval(coeffs, x)
            fluctuation += np.sum((chunk - trend) ** 2)

        # 역방향: 끝에서부터
        remainder = len(integrated) % scale
        if remainder > 0:
            for i in range(n_chunks):
                start = len(integrated) - (i + 1) * scale
                end = start + scale
                if start < 0:
                    break
                chunk = integrated[start:end]
                x = np.arange(len(chunk))
                coeffs = np.polyfit(x, chunk, 1)
                trend = np.polyval(coeffs, x)
                fluctuation += np.sum((chunk - trend) ** 2)

        # RMS fluctuation
        fluctuation = np.sqrt(fluctuation / (2 * n_chunks * scale))
        fluctuations.append(fluctuation)

    # 로그-로그 회귀
    fluctuations = np.array(fluctuations)
    if len(fluctuations) < 2 or np.any(fluctuations <= 0):
        return 1.0

    log_scales = np.log10(scales[:len(fluctuations)])
    log_fluct = np.log10(fluctuations)

    # 기울기 계산 (알파)
    coeffs = np.polyfit(log_scales, log_fluct, 1)
    alpha = coeffs[0]

    return float(alpha)


def _compute_dfa_alpha(path: Path) -> float:
    """
    오디오 파일의 RMS 에너지 시계열에서 DFA 알파값 계산.

    nolds가 있으면 그것 사용, 아니면 numpy 구현.

    Returns:
        float: DFA 알파값
    """
    y, sr = librosa.load(str(path), sr=SR, mono=True)

    # RMS 에너지 시계열 추출
    rms = librosa.feature.rms(y=y)[0]

    if _NOLDS_AVAILABLE:
        # nolds 사용
        try:
            alpha = nolds_dfa(rms, fit="poly")
            return float(alpha)
        except Exception:
            pass  # fallback to numpy

    # numpy 구현
    alpha = _dfa_numpy(rms)
    return float(alpha)


def extract_features(path: Path) -> dict[str, float | str]:
    """단일 오디오 파일에서 네이티브 DFA 알파값을 추출.

    Returns:
        dict with keys: duration_sec, dfa_alpha_native
    """
    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)

    alpha = _compute_dfa_alpha(path)

    return {
        "duration_sec": round(dur, 2),
        "dfa_alpha_native": alpha,
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
            "dfa_alpha": "",           # Essentia 전용
            "danceability_norm": "",   # 나중에 백분위로 채움
            "danceability_clf_prob": "", # Essentia 전용
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
            if (r.get("dfa_alpha_native") or "").strip():
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
        path = _audio_path(band, idx)
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
    전체 표본의 dfa_alpha_native 기준으로 백분위 정규화를 계산.

    danceability_norm = 1 - percentile_rank(dfa_alpha_native)
    (낮은 α = 높은 댄서빌리티 = 1에 가까움)

    returns: dict[idx, danceability_norm]

    ⚠️ 주석: 현재 661곡 파일럿 표본 내부 기준으로 계산.
    전수 확장 시 다시 계산 필요.
    """
    valid_rows = []
    for r in rows:
        alpha_val = r.get("dfa_alpha_native")
        # 숫자이고 error가 없으면 유효
        if alpha_val != "" and r.get("error") == "":
            try:
                float(alpha_val)
                valid_rows.append(r)
            except (ValueError, TypeError):
                continue

    if not valid_rows:
        return {}

    alphas = [float(r["dfa_alpha_native"]) for r in valid_rows]
    alphas_arr = np.array(alphas)

    norms: dict[int, float] = {}
    for r in valid_rows:
        alpha = float(r["dfa_alpha_native"])
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

    ap = argparse.ArgumentParser(
        description="네이티브 DFA 알파값 피처 추출 (참고용, resumable, 병렬)"
    )
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not _AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {_AUDIO_FULL_DIR}")

    print(f"DFA 구현: {_DFA_SOURCE}", flush=True)

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
