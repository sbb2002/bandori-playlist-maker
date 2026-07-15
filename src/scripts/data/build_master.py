"""소스 데이터 3파일을 ``data/``로 복사하고, 전역 ``idx`` 조인으로 canonical
``data/songs_master.csv``를 생성하는 스크립트.

근거:
    - docs/PRD.md §6
    - document-archive 브랜치 archive/reports/2026-07-10-data-team-lead-ticket-design.md §⑤ 티켓1,
      §④ B1(표본 부족 밴드 n>=10 정책)·B2(data/ 복사 정책 / 컬럼 스펙)
    - document-archive 브랜치 archive/reports/2026-07-10-data-team-tickets-2-3-review.md
      (video_id/camelot 컬럼은 기존 모듈 import로 채울 것 — 재구현 금지)

표준 라이브러리만 사용한다 (csv, json, pathlib, sys, collections).

조인 키는 전역 ``idx`` (0-659) 단 하나다. band+song 조인은 원칙적으로 금지 —
단, title이 겹치는 2쌍(raise_a_suilen/R・I・O・T idx 501·525, roselia/Neo-Aspect
idx 570·588)은 2026-07-13 사용자 직접 청취 + key/camelot/tempo_excerpt 완전
일치로 "별개 레코딩이 아니라 동일 음원의 중복 업로드"임이 확인되어, 낮은 idx만
남기고 제거한다(``_CONFIRMED_DUPLICATE_UPLOADS``). 그 결과 master는 658행이다.
``audio_map.json``의 ``songs`` 배열은 위치(리스트 인덱스) == idx 이다(별도 idx
필드 없음).

재실행 가능(멱등): ``data/`` 하위 산출 파일은 매 실행마다 덮어쓴다.

실행:
    python src/scripts/data/build_master.py
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

# ``video_id.py`` / ``camelot.py``는 이 스크립트와 같은 디렉터리에 있다.
# sys.path에 이 디렉터리를 추가해, 실행 위치(cwd)에 관계없이 sibling import가
# 되도록 한다. (기존 test_video_id.py / test_camelot.py와 동일한 import 관례.)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from camelot import to_camelot  # noqa: E402  (기존 모듈, 재구현 금지)
from video_id import extract_video_id  # noqa: E402  (기존 모듈, 재구현 금지)

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------

# .../bandori-playlist-maker/src/scripts/data/build_master.py
#   .parent      -> src/scripts/data
#   .parent.parent -> src/scripts
#   .parent.parent.parent -> src
#   .parent.parent.parent.parent -> bandori-playlist-maker
_REPO_ROOT = _THIS_DIR.parent.parent.parent
_MYPROJECTS_ROOT = _REPO_ROOT.parent

_SOURCE_REPO = _MYPROJECTS_ROOT / "bandori-song-sorter"
_SRC_SONGS_FULL = _SOURCE_REPO / "src" / "content" / "cluster" / "songs_full.csv"
_SRC_FEATURES = (
    _SOURCE_REPO
    / "side-project"
    / "genre-features"
    / "song_features_with_proxies.csv"
)
_SRC_AUDIO_MAP = _SOURCE_REPO / "src" / "content" / "cluster" / "audio_map.json"

_DATA_DIR = _REPO_ROOT / "data"
_DST_SONGS_FULL = _DATA_DIR / "songs_full.csv"
_DST_FEATURES = _DATA_DIR / "song_features_with_proxies.csv"
_DST_AUDIO_MAP = _DATA_DIR / "audio_map.json"
_DST_MASTER = _DATA_DIR / "songs_master.csv"

_EXPECTED_ROW_COUNT = 660

# [2026-07-15 결정] B1 정책(밴드 표본 n>=10 미만 제외)은 폐기한다 — 표본이 적다는
# 이유로 곡을 앱에서 아예 빼는 건 부적절하다는 판단(사용자 확정). eligible_band는
# 이제 실질적으로 항상 True다(밴드 존재만으로 충족되는 문턱). 컬럼 자체는 향후 다른
# 기준(예: 명시적 밴드 차단)을 위해 남겨둔다.
_MIN_BAND_SAMPLE = 1

_MASTER_COLUMNS = [
    "idx",
    "band",
    "song",
    "url",
    "video_id",
    "key",
    "camelot",
    "tempo_excerpt",
    "energy_proxy",
    "mode_score",
    "acousticness_proxy",
    "instrumentalness_proxy",
    "bpm",
    "energy",
    "shape",
    "eligible_band",
]

# 실측 확인된 title 충돌 2쌍 (band, song). 애초에 "별개 레코딩"으로 추정했으나
# 2026-07-13 사용자가 두 영상을 직접 청취해 완전히 동일한 곡임을 확인했고, key·
# camelot·tempo_excerpt까지 소수점 단위로 일치해 교차검증됨 (같은 음원의 중복
# 업로드). band+song 조인은 여전히 원칙적으로 금지하되, 이 2쌍만 확인된 예외로
# 낮은 idx만 남기고 나머지를 제거한다.
_CONFIRMED_DUPLICATE_UPLOADS = {
    ("raise_a_suilen", "R・I・O・T"): {"keep": 501, "drop": 525},
    ("roselia", "Neo-Aspect"): {"keep": 570, "drop": 588},
}
_DROPPED_DUPLICATE_IDXS = {pair["drop"] for pair in _CONFIRMED_DUPLICATE_UPLOADS.values()}


def _copy_sources() -> None:
    """원본 3파일을 무가공(바이트 그대로) 복사한다."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    for src, dst in (
        (_SRC_SONGS_FULL, _DST_SONGS_FULL),
        (_SRC_FEATURES, _DST_FEATURES),
        (_SRC_AUDIO_MAP, _DST_AUDIO_MAP),
    ):
        if not src.is_file():
            raise FileNotFoundError(f"소스 파일을 찾을 수 없습니다: {src}")
        shutil.copyfile(src, dst)


def _read_songs_full() -> dict[int, dict[str, str]]:
    with _DST_SONGS_FULL.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == _EXPECTED_ROW_COUNT, (
        f"songs_full.csv 행 수 불일치: {len(rows)} != {_EXPECTED_ROW_COUNT}"
    )
    by_idx: dict[int, dict[str, str]] = {}
    for r in rows:
        idx = int(r["idx"])
        assert idx not in by_idx, f"songs_full.csv idx 중복: {idx}"
        by_idx[idx] = r
    assert set(by_idx.keys()) == set(range(_EXPECTED_ROW_COUNT)), (
        "songs_full.csv idx 결측/범위 이탈 존재"
    )
    return by_idx


def _read_features() -> dict[int, dict[str, str]]:
    with _DST_FEATURES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == _EXPECTED_ROW_COUNT, (
        f"song_features_with_proxies.csv 행 수 불일치: {len(rows)} != {_EXPECTED_ROW_COUNT}"
    )
    by_idx: dict[int, dict[str, str]] = {}
    for r in rows:
        idx = int(r["idx"])
        assert idx not in by_idx, f"song_features_with_proxies.csv idx 중복: {idx}"
        by_idx[idx] = r
    assert set(by_idx.keys()) == set(range(_EXPECTED_ROW_COUNT)), (
        "song_features_with_proxies.csv idx 결측/범위 이탈 존재"
    )
    return by_idx


def _read_audio_map() -> list[dict]:
    with _DST_AUDIO_MAP.open(encoding="utf-8") as f:
        data = json.load(f)
    songs = data["songs"]
    assert len(songs) == _EXPECTED_ROW_COUNT, (
        f"audio_map.json songs 배열 길이 불일치: {len(songs)} != {_EXPECTED_ROW_COUNT}"
    )
    return songs


def _band_eligibility(songs_full: dict[int, dict[str, str]]) -> dict[str, bool]:
    """밴드별 표본 수(various_artists 포함, 컴필레이션 버킷도 카운트)를 세어
    n>=_MIN_BAND_SAMPLE(=1)이면 True인 eligible_band 맵을 만든다 — 실질적으로 밴드가
    존재하기만 하면 항상 True(B1 정책 폐기, 2026-07-15)."""
    counts = Counter(r["band"] for r in songs_full.values())
    return {band: (n >= _MIN_BAND_SAMPLE) for band, n in counts.items()}


def build() -> dict[str, object]:
    """전체 빌드 파이프라인을 실행하고, 보고용 통계 dict를 반환한다."""
    _copy_sources()

    songs_full = _read_songs_full()
    features = _read_features()
    audio_songs = _read_audio_map()

    # --- idx 조인 시 band/song 불일치 0 검증 (songs_full vs features) ---
    band_song_mismatches = []
    for idx in range(_EXPECTED_ROW_COUNT):
        a, b = songs_full[idx], features[idx]
        if a["band"] != b["band"] or a["song"] != b["song"]:
            band_song_mismatches.append(idx)
    assert not band_song_mismatches, (
        f"idx 조인 시 band/song 불일치: {band_song_mismatches[:10]}"
    )

    # --- idx 조인 시 band/song 불일치 0 검증 (songs_full vs audio_map, 위치==idx) ---
    audio_mismatches = []
    for idx in range(_EXPECTED_ROW_COUNT):
        a, s = songs_full[idx], audio_songs[idx]
        if a["band"] != s["band"] or a["song"] != s["song"]:
            audio_mismatches.append(idx)
    assert not audio_mismatches, (
        f"idx 조인 시 audio_map band/song 불일치: {audio_mismatches[:10]}"
    )

    # --- url 조인 660 일치 (songs_full vs audio_map) ---
    url_matches = sum(
        1
        for idx in range(_EXPECTED_ROW_COUNT)
        if songs_full[idx]["url"] == audio_songs[idx]["url"]
    )
    assert url_matches == _EXPECTED_ROW_COUNT, (
        f"url 조인 불일치: {url_matches}/{_EXPECTED_ROW_COUNT}"
    )

    eligibility = _band_eligibility(songs_full)

    # --- master 행 조립 ---
    master_rows: list[dict[str, object]] = []
    video_ids: set[str] = set()
    for idx in range(_EXPECTED_ROW_COUNT):
        if idx in _DROPPED_DUPLICATE_IDXS:
            continue
        sf = songs_full[idx]
        ft = features[idx]
        am = audio_songs[idx]

        video_id = extract_video_id(sf["url"])
        assert len(video_id) == 11, f"video_id 길이 != 11 (idx={idx}): {video_id!r}"
        video_ids.add(video_id)

        key = ft["key"]
        camelot = to_camelot(key)  # 매핑 누락 시 ValueError -> 그대로 전파(assert 대체)

        row = {
            "idx": idx,
            "band": sf["band"],
            "song": sf["song"],
            "url": sf["url"],
            "video_id": video_id,
            "key": key,
            "camelot": camelot,
            "tempo_excerpt": ft["tempo_excerpt"],
            "energy_proxy": ft["energy_proxy"],
            "mode_score": ft["mode_score"],
            "acousticness_proxy": ft["acousticness_proxy"],
            "instrumentalness_proxy": ft["instrumentalness_proxy"],
            "bpm": am["bpm"],
            "energy": am["energy"],
            "shape": am["shape"],
            "eligible_band": eligibility[sf["band"]],
        }
        master_rows.append(row)

    _expected_master_rows = _EXPECTED_ROW_COUNT - len(_DROPPED_DUPLICATE_IDXS)
    assert len(master_rows) == _expected_master_rows, (
        f"master 행 수 불일치: {len(master_rows)} != {_expected_master_rows}"
    )

    # --- 확인된 중복 업로드 2쌍이 정확히 "keep" idx만 남기고 제거됐는지 검증 ---
    idx_by_row = {r["idx"]: r for r in master_rows}
    for (band, song), pair in _CONFIRMED_DUPLICATE_UPLOADS.items():
        assert pair["drop"] not in idx_by_row, (
            f"중복 업로드 idx {pair['drop']}가 제거되지 않고 master에 남아있음"
        )
        kept = idx_by_row[pair["keep"]]
        assert kept["band"] == band and kept["song"] == song, (
            f"중복 업로드 kept idx {pair['keep']}가 예상 (band,song)과 불일치: "
            f"{kept['band']!r},{kept['song']!r} != {band!r},{song!r}"
        )

    # --- eligible_band False 0행(B1 정책 폐기 — 표본 적다고 제외 안 함, 2026-07-15) ---
    false_rows = [r for r in master_rows if r["eligible_band"] is False]
    assert len(false_rows) == 0, (
        f"eligible_band False 행 존재(정책 폐기 후엔 있으면 안 됨): "
        f"{dict(Counter(r['band'] for r in false_rows))}"
    )

    # --- video_id 전부 11자 (개별 검증은 위 루프에서 완료, 총량 재확인) ---
    assert (
        sum(1 for r in master_rows if len(r["video_id"]) == 11) == _expected_master_rows
    ), "video_id 11자 검증 실패"

    # --- camelot 매핑 누락 0 ---
    assert (
        sum(1 for r in master_rows if r["camelot"]) == _expected_master_rows
    ), "camelot 매핑 누락 존재"

    # --- master 파일 기록 (UTF-8, idx 오름차순) ---
    with _DST_MASTER.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_MASTER_COLUMNS)
        writer.writeheader()
        for row in master_rows:
            writer.writerow(row)

    return {
        "row_count": len(master_rows),
        "eligible_false_count": len(false_rows),
        "eligible_false_bands": {},
        "unique_video_id_count": len(video_ids),
        "dropped_duplicate_upload_idxs": sorted(_DROPPED_DUPLICATE_IDXS),
        "output_files": [
            str(_DST_SONGS_FULL),
            str(_DST_FEATURES),
            str(_DST_AUDIO_MAP),
            str(_DST_MASTER),
        ],
    }


def _make_stdout_safe() -> None:
    """콘솔 출력 인코딩 방어 (부장 반려 재작업, 2026-07-10).

    표준 Windows 콘솔(cp949)에서는 요약 출력의 일본어 곡명(예: R・I・O・T의
    가운뎃점)이 UnicodeEncodeError로 크래시를 일으킨다. stdout/stderr를
    UTF-8 + errors="replace"로 재구성해 어떤 콘솔 인코딩에서도 스크립트가
    정상 종료하도록 한다. CSV/JSON 산출물 인코딩(UTF-8)과는 무관 — 콘솔
    출력 전용 처리이며 파일 기록 로직은 건드리지 않는다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # reconfigure 미지원 스트림(리다이렉트/커스텀 래퍼 등)은 그대로
            # 둔다. 표준 콘솔에서는 항상 성공한다.
            pass


def main() -> None:
    _make_stdout_safe()
    stats = build()
    print("build_master.py: 전 검증(assert) 통과.")
    print(f"  master 행 수: {stats['row_count']}")
    print(f"  eligible_band False 행 수: {stats['eligible_false_count']}")
    print(f"  eligible_band False 밴드별 구성: {stats['eligible_false_bands']}")
    print(f"  고유 video_id 수: {stats['unique_video_id_count']}")
    print(f"  제거된 중복 업로드 idx: {stats['dropped_duplicate_upload_idxs']}")
    print("  산출 파일:")
    for path in stats["output_files"]:
        print(f"    - {path}")


if __name__ == "__main__":
    main()
