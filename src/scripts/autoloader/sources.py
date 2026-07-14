"""형제 레포(bandori-song-sorter) origin/main 데이터 읽기 + 신곡 감별.

신곡 **감지**(RSS·Telegram)는 형제 프로젝트의 Actions 파이프라인이 전담한다(사용자
확정 2026-07-15). 이 모듈은 감지가 아니라 **감별**만 한다: 형제 origin/main에 이미
반영된 곡 중 우리 `data/songs_master.csv`에 없는 곡을 골라낸다.

형제 레포 접근 방식: 데브 워킹트리를 건드리지 않도록 `git fetch origin` 후
`git show origin/main:<path>`로 블롭만 읽는다(read-only — CLAUDE.md의 "형제 레포
읽기 전용" 원칙 준수). 전용 클론(../bandori-pipeline)의 신선도에 의존하지 않는다.

감별 규칙(재시도 안전·멱등):
  후보 = 형제 songs_full.csv 행 중
         (a) video_id가 master에 없음, 그리고
         (b) idx가 build_master의 확인된 중복 업로드 drop 목록에 없음.
  (a)만으로는 master에서 의도적으로 제거된 중복 업로드(idx 525·588)가 후보로 재등장
  하므로 (b)가 필요하다. idx 기준 "max+1 이후"만 보는 규칙은 부분 실패(가운데 곡만
  실패) 시 재시도가 누락되므로 쓰지 않는다.

표준 라이브러리만 사용.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
# .../bandori-playlist-maker/src/scripts/autoloader/sources.py
#   parents[0]=autoloader, [1]=scripts, [2]=src, [3]=repo root
REPO_ROOT = _THIS_DIR.parents[2]

# 기존 모듈 재사용(재구현 금지 규칙): video_id 추출 + 중복 업로드 drop 목록.
_DATA_SCRIPTS = _THIS_DIR.parent / "data"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

from build_master import _CONFIRMED_DUPLICATE_UPLOADS  # noqa: E402
from video_id import extract_video_id  # noqa: E402

DROPPED_DUPLICATE_IDXS = {p["drop"] for p in _CONFIRMED_DUPLICATE_UPLOADS.values()}

DEFAULT_SORTER_REPO = REPO_ROOT.parent / "bandori-song-sorter"
SORTER_SONGS_FULL = "src/content/cluster/songs_full.csv"
SORTER_AUDIO_MAP = "src/content/cluster/audio_map.json"
MAIN_REF = "origin/main"


class SorterError(RuntimeError):
    """형제 레포 접근 실패(경로/네트워크/ref)."""


def _git(sorter_repo: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(sorter_repo), *args],
                       capture_output=True)
    if p.returncode != 0:
        raise SorterError(
            f"git {' '.join(args[:3])}… 실패(rc={p.returncode}): "
            f"{p.stderr.decode('utf-8', errors='replace').strip()[:300]}")
    return p.stdout


def fetch_sorter(sorter_repo: Path = DEFAULT_SORTER_REPO) -> None:
    """형제 레포에서 origin을 fetch(워킹트리 무접촉, remote-tracking ref만 갱신)."""
    if not (sorter_repo / ".git").exists():
        raise SorterError(f"형제 레포 없음: {sorter_repo}")
    _git(sorter_repo, "fetch", "origin", "--prune")


def read_main_bytes(relpath: str, sorter_repo: Path = DEFAULT_SORTER_REPO) -> bytes:
    """origin/main의 파일 내용을 바이트 그대로 반환(통째 복사용)."""
    return _git(sorter_repo, "show", f"{MAIN_REF}:{relpath}")


def load_sorter_songs_full(sorter_repo: Path = DEFAULT_SORTER_REPO) -> list[dict]:
    text = read_main_bytes(SORTER_SONGS_FULL, sorter_repo).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def load_sorter_audio_map(sorter_repo: Path = DEFAULT_SORTER_REPO) -> dict:
    return json.loads(read_main_bytes(SORTER_AUDIO_MAP, sorter_repo).decode("utf-8"))


def load_master_rows(master_csv: Path) -> list[dict]:
    with master_csv.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def detect_new(sorter_rows: list[dict], master_rows: list[dict]) -> list[dict]:
    """형제 main에는 있고 master에는 없는 곡 목록(idx 오름차순).

    반환 항목: {"idx": int, "band", "song", "url", "video_id"}.
    """
    known = {(r.get("video_id") or "").strip() for r in master_rows}
    known.discard("")
    out = []
    for r in sorter_rows:
        idx = int(r["idx"])
        if idx in DROPPED_DUPLICATE_IDXS:
            continue
        vid = extract_video_id(r["url"])
        if vid in known:
            continue
        out.append({"idx": idx, "band": r["band"], "song": r["song"],
                    "url": r["url"], "video_id": vid})
    out.sort(key=lambda c: c["idx"])
    return out


def audio_map_entries_by_idx(audio_map: dict) -> dict[int, dict]:
    """audio_map.json의 songs 배열(위치==idx)을 idx→entry dict로 변환."""
    return {i: s for i, s in enumerate(audio_map["songs"])}
