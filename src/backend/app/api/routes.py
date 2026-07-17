"""API 라우트 — POST /api/setlist, GET /api/health.

어댑터·데이터는 request.app.state에서 꺼내 쓴다(주입은 main.py). 도메인 에러는 여기서
잡지 않고 그대로 전파하여 main.py의 예외 핸들러가 스키마3 에러 포맷으로 매핑한다.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request, Response

from ..domain.models import MoodParameters, StageSpec
from ..domain.selection import DEFAULT_AVG_SONG_SECONDS, build_setlist
from .band_aliases import detect_bands
from .schemas import SetlistRequest, serialize_setlist

router = APIRouter()

_DEFAULT_TARGET_MINUTES = 60
_MAX_TARGET_MINUTES = 180  # 최장 3시간 — 사용자 입력·LLM·단계 그래프 어느 경로로 와도 이 값으로 고정


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


def _resolve_song_type(inc_original, inc_cover, song_type: str) -> tuple[bool, bool]:
    """(include_original, include_cover) 결정. 사용자가 체크박스를 명시(None 아님)하면 그 값,
    아니면 LLM song_type("all"|"original"|"cover")으로. 기본(all)=둘 다 포함=ALL."""
    if inc_original is None and inc_cover is None:
        return (song_type in ("all", "original"), song_type in ("all", "cover"))
    return (bool(inc_original), bool(inc_cover))


@router.get("/api/health")
def health(request: Request) -> dict:
    # 활성 무드 해석기(stub|groq|openrouter)를 노출 — 라이브가 오프라인 스텁으로 떨어졌는지 즉시 확인용.
    # (스텁 요약 "은은한 한결같은 흐름의…"가 고정되면 GROQ_API_KEY 미설정으로 스텁 폴백된 것.)
    name = getattr(request.app.state, "interpreter_name", "") or ""
    mode = (
        "stub" if "Stub" in name
        else "groq" if "Groq" in name
        else "openrouter" if "OpenRouter" in name
        else (name or "unknown")
    )
    return {
        "status": "ok",
        "version": getattr(request.app.state, "version", "dev"),
        "interpreter": mode,
    }


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
            # 검색 보조(로마자·한글 음차·한자음) — pykakasi/hanja로 로드 시 1회 계산된 캐시값(§ja_transliteration).
            "song_romaji": s.song_romaji,
            "song_hangul": s.song_hangul,
            "song_hanja_reading": s.song_hanja_reading,
        }
        for s in request.app.state.songs
    ]
    songs.sort(key=lambda x: (x["band"], x["song"].lower()))
    return {"songs": songs}


@router.post("/api/setlist")
def create_setlist(payload: SetlistRequest, request: Request, response: Response) -> dict:
    # 응답 캐시 금지 — 매 요청 새로 생성되는 결과가 브라우저/프록시에 캐시돼 요약 카드가 '고착'되지
    # 않도록 방지(사용자 보고: 캐시 지우기 전까지 동일 요약 유지).
    response.headers["Cache-Control"] = "no-store"

    interpreter = request.app.state.interpreter

    params: MoodParameters = interpreter.interpret(payload.prompt, payload.previous_prompt)

    # 핫픽스(세부설정 우선순위): 'honor'는 **재생 형태 설정**(에너지 아크·단계 수·재생시간)에만 적용.
    # 직전 요청과 의도가 본질적으로 같을 때만 사용자가 건드린 이 값들을 존중하고, 1회차이거나 의도가
    # 바뀌면(honor=False) 무시하고 모델이 새로 제어한다(프롬프트 바꿔도 옛 아크가 고착되던 버그 해소).
    # ※ **스코프 필터(밴드·커버)는 honor와 무관하게 항상 적용** — 사용자가 명시적으로 좁힌 범위라
    #   프롬프트 mood와 독립적으로 지속되어야 한다(밴드 셀렉터가 2회차에 무시되던 문제 해소).
    honor = bool(payload.previous_prompt) and bool(params.same_as_previous)

    # 커버/오리지널(스코프 필터): 프롬프트 의도와 무관하게 항상 사용자 명시값을 존중(없으면 LLM song_type).
    inc_original, inc_cover = _resolve_song_type(
        payload.include_original, payload.include_cover, params.song_type
    )
    songs = _apply_cover_filter(request.app.state.songs, inc_original, inc_cover)

    # 밴드 필터(설정 §5-1b, 스코프 필터): 항상 적용 — 수동 선택 밴드 ∪ 현재 프롬프트 자동감지.
    band_names = {b.strip() for b in (payload.bands or []) if b and b.strip()}
    band_names |= detect_bands(payload.prompt)  # 현재 프롬프트에 밴드명(별명) 언급 시 자동 필터
    band_filter = band_names or None

    # 사용자 지정 단계(설정 §5-1a): honor일 때만 에너지 아크·곡 수를 강제(그래프 수동, 최대 11구간).
    stage_specs = None
    if honor and payload.stages:
        stage_specs = [
            StageSpec(
                energy_target=st.energy,
                song_count=st.song_count
                if st.song_count is not None
                else max(1, round(st.minutes * 60 / DEFAULT_AVG_SONG_SECONDS)),
            )
            for st in payload.stages
        ]
        # 단계별로는 각각 180분/60곡 이하로 제한돼 있지만(schemas.py), 최대 11단계 합산은
        # 그 상한을 훌쩍 넘길 수 있다 — 합산 재생시간도 최장 3시간으로 비례 축소.
        max_total_songs = max(1, round(_MAX_TARGET_MINUTES * 60 / DEFAULT_AVG_SONG_SECONDS))
        total_songs = sum(s.song_count for s in stage_specs)
        if total_songs > max_total_songs:
            scale = max_total_songs / total_songs
            stage_specs = [replace(s, song_count=max(1, round(s.song_count * scale))) for s in stage_specs]

    # 요청이 명시한 값은(honor일 때만) LLM 해석을 override(architecture.md 스키마3).
    if stage_specs is not None:
        stage_count = len(stage_specs)
        minutes = round(sum(s.song_count for s in stage_specs) * DEFAULT_AVG_SONG_SECONDS / 60)
    else:
        stage_count = payload.stage_count if (honor and payload.stage_count is not None) else params.stage_count
        stage_count = max(2, min(11, stage_count))
        minutes = payload.target_minutes if (honor and payload.target_minutes is not None) else params.target_minutes
        if minutes is None:
            minutes = _DEFAULT_TARGET_MINUTES
        minutes = max(10, min(_MAX_TARGET_MINUTES, minutes))

    effective = replace(params, stage_count=stage_count, target_minutes=minutes)
    setlist = build_setlist(
        songs, effective, target_seconds=minutes * 60,
        band_filter=band_filter, stage_specs=stage_specs,
    )
    result = serialize_setlist(setlist)
    # 실제 적용된 밴드 필터(프롬프트 자동감지 포함) — 프론트가 체크박스 동기화에 사용.
    result["applied_bands"] = sorted(band_filter) if band_filter else []
    # 실제 적용된 곡 종류(커버/오리지널) — 프론트가 체크박스 반영에 사용.
    result["include_original"] = inc_original
    result["include_cover"] = inc_cover
    # 재생 형태 override(에너지 아크·단계·재생시간)를 존중했는지 — 프론트가 자동 해석 시 그래프/재생시간을
    # 새 해석으로 되돌리는 데 사용(밴드·커버 스코프 필터는 항상 적용이라 무관).
    result["honored_overrides"] = honor
    return result
