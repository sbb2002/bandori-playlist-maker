"""조성(key) 추출: Essentia KeyExtractor 교차검증.

배경 / 개념
-----------
Essentia의 KeyExtractor를 사용한 교차검증. HPCP(Harmonic Pitch Class Profile)
기반 별도 알고리즘으로 키를 추출해 Krumhansl-Kessler 결과와 비교한다.

**현재 환경(Windows) 실행 불가** — 이 스크립트는 WSL2 환경에서만 실행 가능.
Essentia 라이브러리가 없으면 import 실패 후 명확한 메시지와 함께 종료한다.

산출물
------
이미 있는 `out/key_raw.csv`를 읽고 essentia 관련 컬럼만 병합해 덮어쓴다:
- `key_essentia` — Essentia 추출 키
- `mode_essentia` — Essentia 추출 모드(major/minor)
- `key_mismatch` — K-S와 Essentia 키가 다름 (bool)
- `mode_only_mismatch` — 키는 같은데 모드만 다름 (bool, 근접조 판정 포함)

실행 (WSL2만)
-----
    wsl python src/extract_key_essentia.py
    wsl python src/extract_key_essentia.py --workers 4
    wsl python src/extract_key_essentia.py --limit 5  # 테스트
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 환경 체크: Essentia 라이브러리 필수
# ---------------------------------------------------------------------------
try:
    import essentia.standard as es
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False

if not ESSENTIA_AVAILABLE:
    print(
        "[ERROR] Essentia 라이브러리를 찾을 수 없습니다.\n"
        "WSL2 환경에서만 이 스크립트를 실행할 수 있습니다.\n"
        "\n"
        "WSL2에서 Essentia 설치:\n"
        "  pip install essentia-tensorflow\n"
        "\n"
        "또는 별도의 WSL2 Essentia 패키지 문서를 참고하세요.",
        file=sys.stderr,
    )
    sys.exit(1)

import numpy as np

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
OUT_CSV = OUT_DIR / "key_raw.csv"

# 추출 파라미터
SR = 22050

# 음이름 (인덱스는 C=0, ..., B=11)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 근접조(relative key) 매핑: major -> relative minor (3음 내림)
# 예: C major의 관계조는 A minor
RELATIVE_KEY_MAP = {
    # major -> minor
    ("C", "major"): ("A", "minor"),
    ("C#", "major"): ("A#", "minor"),
    ("D", "major"): ("B", "minor"),
    ("D#", "major"): ("C#", "minor"),
    ("E", "major"): ("C#", "minor"),
    ("F", "major"): ("D", "minor"),
    ("F#", "major"): ("D#", "minor"),
    ("G", "major"): ("E", "minor"),
    ("G#", "major"): ("F#", "minor"),
    ("A", "major"): ("F#", "minor"),
    ("A#", "major"): ("G#", "minor"),
    ("B", "major"): ("G#", "minor"),
    # minor -> major (역방향)
    ("A", "minor"): ("C", "major"),
    ("A#", "minor"): ("C#", "major"),
    ("B", "minor"): ("D", "major"),
    ("C#", "minor"): ("E", "major"),
    ("D", "minor"): ("F", "major"),
    ("D#", "minor"): ("F#", "major"),
    ("E", "minor"): ("G", "major"),
    ("F#", "minor"): ("A", "major"),
    ("F#", "minor"): ("G#", "major"),  # 주: G#는 A#와도 관계조
    ("G#", "minor"): ("B", "major"),
}


def _is_relative_key(key1: str, mode1: str, key2: str, mode2: str) -> bool:
    """두 키가 근접조(relative key) 관계인지 판정.

    근접조: C major와 A minor처럼 같은 스케일을 공유하지만 다른 뿌리음을 가진 경우.
    """
    pair1 = (key1, mode1)
    pair2 = (key2, mode2)

    # 정확한 근접조 관계 확인
    if pair1 in RELATIVE_KEY_MAP and RELATIVE_KEY_MAP[pair1] == pair2:
        return True
    if pair2 in RELATIVE_KEY_MAP and RELATIVE_KEY_MAP[pair2] == pair1:
        return True

    return False


def _essentia_key_to_note(key_str: str) -> str:
    """Essentia KeyExtractor 출력(C, C#, ... B)을 음이름으로 변환(이미 표준형).

    Essentia는 이미 표준 음이름을 반환하므로 그대로 사용.
    """
    return key_str


def extract_essentia_key(path: Path) -> tuple[str | None, str | None]:
    """Essentia KeyExtractor로 키 추출.

    반환: (key, mode) where mode is "major" or "minor"
    실패하면 (None, None)
    """
    try:
        loader = es.MonoLoader(filename=str(path), sampleRate=SR)
        audio = loader()

        key_extractor = es.KeyExtractor()
        key, scale, strength = key_extractor(audio)

        # Essentia 출력: key는 음이름(C, C#, ..., B), scale은 "major"/"minor"
        return key, scale.lower()
    except Exception:
        return None, None


def _load_master() -> list[dict[str, str]]:
    """songs_master.csv 로드."""
    with MASTER_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _audio_path(band: str, idx: int) -> Path:
    return AUDIO_FULL_DIR / f"{band}__{idx:03d}.wav"


def _worker(task: tuple[int, str, str, str]) -> dict:
    """멀티프로세싱 워커. (idx, band, song, path) → 결과 행."""
    idx, band, song, path = task
    t0 = time.time()
    try:
        key_ess, mode_ess = extract_essentia_key(Path(path))
        return {
            "idx": idx,
            "key_essentia": key_ess or "",
            "mode_essentia": mode_ess or "",
            "error": "",
        }
    except Exception as exc:
        return {
            "idx": idx,
            "key_essentia": "",
            "mode_essentia": "",
            "error": repr(exc),
        }


def _build_tasks(
    rows: list[dict[str, str]],
    only_idx: set[int] | None,
    limit: int | None,
) -> list[tuple[int, str, str, str]]:
    """처리 대상 곡 리스트 생성."""
    tasks: list[tuple[int, str, str, str]] = []
    for r in rows:
        idx = int(r["idx"])
        if only_idx is not None and idx not in only_idx:
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


def merge_essentia_results(
    csv_path: Path, essentia_results: dict[int, dict]
) -> None:
    """기존 key_raw.csv를 읽고 essentia 컬럼을 병합해서 덮어쓴다."""
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # essentia 결과 병합 및 비교
    for row in rows:
        idx = int(row["idx"])
        if idx in essentia_results:
            ess_res = essentia_results[idx]
            row["key_essentia"] = ess_res.get("key_essentia", "")
            row["mode_essentia"] = ess_res.get("mode_essentia", "")

            # key_mismatch, mode_only_mismatch 계산
            key_ks = row.get("key_ks", "").strip()
            mode_ks = row.get("mode_ks", "").strip()
            key_ess = row.get("key_essentia", "").strip()
            mode_ess = row.get("mode_essentia", "").strip()

            if key_ks and key_ess and mode_ks and mode_ess:
                # 키가 다른 경우
                if key_ks != key_ess:
                    # 근접조(relative key)인지 확인
                    if _is_relative_key(key_ks, mode_ks, key_ess, mode_ess):
                        # 근접조는 key_mismatch=False, mode_only_mismatch=False
                        # (구분 가능한 키이지만 관계조임)
                        row["key_mismatch"] = "False"
                        row["mode_only_mismatch"] = "False"
                    else:
                        # 진정한 불일치
                        row["key_mismatch"] = "True"
                        row["mode_only_mismatch"] = "False"
                else:
                    # 키가 같은 경우
                    if mode_ks != mode_ess:
                        row["key_mismatch"] = "False"
                        row["mode_only_mismatch"] = "True"
                    else:
                        # 완벽히 일치
                        row["key_mismatch"] = "False"
                        row["mode_only_mismatch"] = "False"
            else:
                # essentia 추출 실패한 경우
                row["key_mismatch"] = ""
                row["mode_only_mismatch"] = ""

    # 덮어쓰기
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    if not OUT_CSV.exists():
        print(f"[ERROR] {OUT_CSV}가 없습니다.", file=sys.stderr)
        print(
            "먼저 extract_key_ks.py를 실행해서 Krumhansl-Kessler 결과를 생성하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    ap = argparse.ArgumentParser(description="조성(key) 추출: Essentia 교차검증 (WSL2)")
    ap.add_argument("--workers", type=int, default=4, help="병렬 worker 수(기본 4)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--idx", type=str, default=None, help="특정 idx만 (쉼표구분). 재추출.")
    args = ap.parse_args()

    if not AUDIO_FULL_DIR.is_dir():
        raise FileNotFoundError(f"오디오 디렉터리 없음: {AUDIO_FULL_DIR}")

    rows = _load_master()
    only_idx = {int(x) for x in args.idx.split(",") if x.strip()} if args.idx else None
    tasks = _build_tasks(rows, only_idx, args.limit)

    print(
        f"전체 {len(rows)}곡, 이번 Essentia 검증 {len(tasks)}곡, worker={args.workers}",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다.", flush=True)
        return

    n_ok = n_err = 0
    essentia_results = {}
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
            essentia_results[idx] = res

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
    except Exception as e:
        print(f"[ERROR] 처리 중 오류: {e}", file=sys.stderr)
        sys.exit(1)

    # 결과 병합
    print("결과 병합 중...", flush=True)
    merge_essentia_results(OUT_CSV, essentia_results)

    print(f"완료: ok={n_ok} err={n_err}  총 {(time.time()-t_start)/60:.1f}분", flush=True)
    print(f"산출: {OUT_CSV} (essentia 컬럼 병합)", flush=True)


if __name__ == "__main__":
    main()
