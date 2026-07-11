"""API 라우트 — POST /api/setlist, GET /api/health.

어댑터·데이터는 request.app.state에서 꺼내 쓴다(주입은 main.py). 도메인 에러는 여기서
잡지 않고 그대로 전파하여 main.py의 예외 핸들러가 스키마3 에러 포맷으로 매핑한다.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request

from ..domain.models import MoodParameters, StageSpec
from ..domain.selection import DEFAULT_AVG_SONG_SECONDS, build_setlist
from .band_aliases import detect_bands
from .schemas import SetlistRequest, serialize_setlist

router = APIRouter()

_DEFAULT_TARGET_MINUTES = 60


def _is_cover(song) -> bool:
    """커버 곡 판정 — 제목의 '(Cover)' 표기 기준(데이터 관례)."""
    return "(cover)" in song.song.lower()


def _apply_cover_filter(songs, include_original: bool, include_cover: bool):
    """오리지널/커버 필터(사용자 추가제안). 둘 다 같으면(모두 체크/모두 해제) ALL."""
    if include_original == include_cover:
        return songs
    if include_original:
        return [s for s in songs if not _is_cover(s)]
    return [s for s in songs if _is_cover(s)]


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/bands")
def list_bands(request: Request) -> dict:
    """후보(eligible) 밴드 목록 + 곡 수 — 프론트 밴드 필터 체크박스용(설정 §5-1b)."""
    counts: dict[str, int] = {}
    for s in request.app.state.songs:
        if s.eligible_band:
            counts[s.band] = counts.get(s.band, 0) + 1
    bands = [{"band": b, "count": n} for b, n in counts.items()]
    bands.sort(key=lambda x: (-x["count"], x["band"]))
    return {"bands": bands}


@router.get("/api/songs")
def list_songs(request: Request) -> dict:
    """전체 곡 목록 — 프론트 '곡 추가' 미니 브라우저용(밴드/곡 선택). 삽입·재생에 필요한
    필드만 반환(idx·band·song·video_id·camelot·energy). 밴드→곡 순 정렬."""
    songs = [
        {
            "idx": s.idx,
            "band": s.band,
            "song": s.song,
            "video_id": s.video_id,
            "camelot": s.camelot,
            "energy": round(s.energy, 3),
        }
        for s in request.app.state.songs
    ]
    songs.sort(key=lambda x: (x["band"], x["song"].lower()))
    return {"songs": songs}


@router.post("/api/setlist")
def create_setlist(payload: SetlistRequest, request: Request) -> dict:
    interpreter = request.app.state.interpreter
    songs = _apply_cover_filter(
        request.app.state.songs, payload.include_original, payload.include_cover
    )

    params: MoodParameters = interpreter.interpret(payload.prompt)

    # 밴드 필터(설정 §5-1b): 빈 목록/미지정 = ALL.
    band_names = {b.strip() for b in (payload.bands or []) if b and b.strip()}
    band_names |= detect_bands(payload.prompt)  # 프롬프트에 밴드명(별명) 언급 시 자동 필터
    band_filter = band_names or None

    # 사용자 지정 단계(설정 §5-1a): 있으면 에너지 아크·곡 수를 강제.
    stage_specs = None
    if payload.stages:
        stage_specs = [
            StageSpec(
                energy_target=st.energy,
                song_count=st.song_count
                if st.song_count is not None
                else max(1, round(st.minutes * 60 / DEFAULT_AVG_SONG_SECONDS)),
            )
            for st in payload.stages
        ]

    # 요청이 명시한 값은 LLM 해석을 override(architecture.md 스키마3).
    if stage_specs is not None:
        stage_count = len(stage_specs)
        minutes = round(sum(s.song_count for s in stage_specs) * DEFAULT_AVG_SONG_SECONDS / 60)
    else:
        stage_count = payload.stage_count if payload.stage_count is not None else params.stage_count
        stage_count = max(2, min(5, stage_count))
        minutes = payload.target_minutes if payload.target_minutes is not None else params.target_minutes
        if minutes is None:
            minutes = _DEFAULT_TARGET_MINUTES
        minutes = max(10, min(180, minutes))

    effective = replace(params, stage_count=stage_count, target_minutes=minutes)
    setlist = build_setlist(
        songs, effective, target_seconds=minutes * 60,
        band_filter=band_filter, stage_specs=stage_specs,
    )
    result = serialize_setlist(setlist)
    # 실제 적용된 밴드 필터(프롬프트 자동감지 포함) — 프론트가 체크박스 동기화에 사용.
    result["applied_bands"] = sorted(band_filter) if band_filter else []
    return result
