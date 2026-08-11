"""API 라우트 — POST /api/setlist, GET /api/health.

어댑터·데이터는 request.app.state에서 꺼내 쓴다(주입은 main.py). 도메인 에러는 여기서
잡지 않고 그대로 전파하여 main.py의 예외 핸들러가 스키마3 에러 포맷으로 매핑한다.
"""

from __future__ import annotations

import logging
import os
import secrets
import statistics
from dataclasses import replace

from fastapi import APIRouter, Header, HTTPException, Request, Response

from ..domain.models import MoodParameters, StageSpec
from ..domain.selection import (
    DEFAULT_AVG_SONG_SECONDS,
    build_setlist,
    resolve_stage_bands,
    resolve_stage_impression_text,
)
from ..repo.song_repo import AUDIO_FEATURE_COLS
from .band_aliases import detect_bands
from .schemas import SetlistRequest, serialize_setlist

router = APIRouter()
logger = logging.getLogger("setlist_maker")

_DEFAULT_TARGET_MINUTES = 60
_MAX_TARGET_MINUTES = 180  # 최장 3시간 — 사용자 입력·LLM·단계 그래프 어느 경로로 와도 이 값으로 고정
# 표본이 이 미만인 밴드는 feature_stats 프롬프트 블록에서 제외(선곡 후보 풀에서 빼는 게
# 아니라 LLM 프롬프트 텍스트에서만 — 후자는 _MIN_BAND_SAMPLE=1로 항상 전 밴드 포함).
# n=2~5 표본의 mean/std는 통계적으로 거의 무의미해 토큰만 쓰고 신호는 약하다(2026-08-10 실측:
# 소수 밴드 3개 제외로 feature_stats 블록 토큰 -21%).
_MIN_BAND_STATS_SAMPLE = 10


def _feature_stats(pool) -> dict | None:
    """오디오 지표 6종의 분포 통계(전체 + 밴드별 min/max/mean/median/std).

    LLM이 stage_params 값을 실제 곡 분포에 근거해 고르게 하는 프롬프트 재료
    (관찰된 문제: 분포 정보가 없으면 중앙값 근처에 소극적으로 안주). 값은 Song에
    적재된 minmax 스케일(0~1) 그대로 — UI 슬라이더·stage_params와 동일 스케일.
    지표 컬럼이 없는 데이터(구 스냅샷·테스트 픽스처)면 None. 표본이 _MIN_BAND_STATS_SAMPLE
    미만인 밴드는 통계가 신뢰하기 어려워 블록에서 제외한다(전체 통계는 항상 포함).
    """
    def _group(songs) -> dict[str, dict[str, float]]:
        out = {}
        for field in AUDIO_FEATURE_COLS:
            values = [v for s in songs if (v := getattr(s, field)) is not None]
            if not values:
                continue
            out[field] = {
                "min": min(values),
                "max": max(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
                "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
            }
        return out

    total = _group(pool)
    if not total:
        return None
    stats = {"전체": total}
    for band in sorted({s.band for s in pool}):
        band_songs = [s for s in pool if s.band == band]
        if len(band_songs) < _MIN_BAND_STATS_SAMPLE:
            continue
        band_stats = _group(band_songs)
        if band_stats:
            stats[band] = band_stats
    return stats


def _build_stage_impression_vectors(embedder, impression_texts: list[str | None]) -> list[list[float] | None] | None:
    """스테이지별 가사 감상 텍스트(우선순위 해석 완료)를 임베딩 어댑터로 벡터화한다(프로토타입).

    텍스트는 `domain.selection.resolve_stage_impression_text()`로 이미 스펙 우선/LLM 폴백
    규칙을 거친 최종값 — AI 모드(LLM stage_params)든 커스텀 모드(사용자 수동 입력)든 동일하게
    처리된다. 도메인(`build_setlist`)은 임베딩 모델을 직접 호출하지 않는다는 원칙에 따라
    라우트(조립 지점)에서 미리 계산해 넘긴다. 임베딩 실패(모델 로드 실패 등)는 이 신호 없이
    (중립) 계속 진행 — 가사 유사도는 4순위 타이브레이크일 뿐이라 실패해도 선곡 자체는 막히지 않는다.
    """
    if not impression_texts or not any(impression_texts):
        return None
    vectors: list[list[float] | None] = []
    for text in impression_texts:
        if not text:
            vectors.append(None)
            continue
        try:
            vectors.append(embedder.embed(text))
        except Exception:  # noqa: BLE001 — 임베딩 실패는 이 스테이지만 중립 처리하고 계속
            logger.warning("스테이지 impression 임베딩 실패 — 이 스테이지는 가사 유사도 없이 진행.", exc_info=True)
            vectors.append(None)
    return vectors


def _validate_stage_bands(
    stage_bands: list[str | None] | None, detected_bands: set[str]
) -> list[str | None] | None:
    """LLM이 산출한 stage_bands 값을 실제로 이 요청에서 감지된 밴드로만 제한한다(프로토타입).

    각 원소는 LLM이 사용자 표현 그대로(별명 포함) 적은 자유 텍스트일 수 있으므로, 그 텍스트를
    다시 `detect_bands()`(band_aliases.py의 결정적 별명 매칭)에 통과시켜 정규 밴드 id로
    바꾼다. 정확히 밴드 1개로 좁혀지지 않거나, 그 밴드가 `detected_bands`(이 프롬프트에서
    실제로 언급된 밴드 집합 — band_filter의 근거와 동일)에 없으면 무조건 None으로 무효화한다.
    LLM이 언급되지 않은 밴드를 지어내거나 애매하게 적어도 그 스테이지는 밴드 제한 없이(중립)
    진행되도록 하는 안전장치.
    """
    if not stage_bands:
        return stage_bands
    validated: list[str | None] = []
    for raw in stage_bands:
        band: str | None = None
        if raw:
            resolved = detect_bands(raw)
            if len(resolved) == 1:
                candidate = next(iter(resolved))
                if candidate in detected_bands:
                    band = candidate
        validated.append(band)
    return validated


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
            "song_hangul_search": s.song_hangul_search,
            "song_hanja_reading": s.song_hanja_reading,
        }
        for s in request.app.state.songs
    ]
    songs.sort(key=lambda x: (x["band"], x["song"].lower()))
    return {"songs": songs}


def _run_setlist(payload: SetlistRequest, state) -> dict:
    """실제 세트리스트 생성(LLM 해석 + 선곡 + 직렬화). AI 모드는 이 안에서 interpreter.interpret()가
    TPM 리미터에 블로킹될 수 있다 — 그래서 create_setlist가 이 함수를 커스텀 모드만 직접(동기)
    호출하고, AI 모드는 jobs.JobStore를 통해 백그라운드 스레드에서 돌린다. `state`는
    `request.app.state`(Starlette State) — 백그라운드 잡은 Request 객체가 없어 이렇게 분리했다.
    """
    interpreter = state.interpreter

    # 밴드 필터(설정 §5-1b, 스코프 필터): 항상 적용 — 수동 선택 밴드 ∪ 현재 프롬프트 자동감지.
    # interpreter.interpret() 호출 전에 계산 (band_filter는 LLM 결과에 의존하지 않음).
    band_names = {b.strip() for b in (payload.bands or []) if b and b.strip()}
    band_names |= detect_bands(payload.prompt or "")  # 현재 프롬프트에 밴드명(별명) 언급 시 자동 필터
    band_filter = band_names or None

    # AI 모드 vs 커스텀 모드 분기
    if payload.mode == "custom":
        # 커스텀 모드: LLM 호출 안 함, stages 필수
        if not payload.stages:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_REQUEST", "message": "커스텀 모드는 stages가 필요합니다."}}
            )
        # 사용자가 직접 지정한 단계들로부터 MoodParameters 구성. brightness=0.0은 placeholder일
        # 뿐 실제로 아무 데도 안 쓰인다 — 선곡(selection.py)은 2026-08-11부터 mode_score/shape
        # 기반 밝기 축을 완전히 제거했고(에너지+신규 지표 6종 통합거리로 대체), 커스텀 모드의
        # "밝기" 슬라이더는 이미 stage 각각의 valence(StageSpec.valence)로 따로 전달된다.
        params = MoodParameters(
            brightness=0.0,
            start_energy=payload.stages[0].energy,
            end_energy=payload.stages[-1].energy,
            stage_count=len(payload.stages),
            target_minutes=payload.target_minutes,
            interpretation_summary="",
            stage_energies=[s.energy for s in payload.stages],
            tags=[],
            song_type="all",
            same_as_previous=None,
        )
        honor = True  # 커스텀 모드는 항상 사용자 설정을 존중
    else:
        # AI 모드: 기존 로직
        # band_filter를 이용해 현재 필터 곡 풀의 에너지 분포 통계 계산 (3차 LLM 프롬프트용).
        pool = [s for s in state.songs if not band_filter or s.band in band_filter]
        if pool:
            energies = [s.energy for s in pool]
            energy_stats = {
                "min": min(energies),
                "max": max(energies),
                "mean": statistics.fmean(energies),
                "std": statistics.pstdev(energies) if len(energies) > 1 else 0.0,
            }
        else:
            energy_stats = None

        params = interpreter.interpret(
            payload.prompt, payload.previous_prompt,
            energy_stats=energy_stats, feature_stats=_feature_stats(pool),
        )
        # 프로토타입: LLM이 지어낸 stage_bands 값을 이 프롬프트에서 실제로 감지된 밴드로만
        # 제한(band_names는 위에서 이미 detect_bands(payload.prompt)를 포함해 계산됨).
        params = replace(params, stage_bands=_validate_stage_bands(params.stage_bands, band_names))

        # DEPRECATED(2026-08-03, 3단계): 예전엔 'honor'를 "직전 요청과 의도가 같은가"
        # (params.same_as_previous)로 판정해, 같을 때만 사용자가 건드린 세부설정(에너지
        # 아크·단계 수·재생시간)을 존중했다 — AI/커스텀 모드가 나뉘기 전, 한 화면에서
        # 프롬프트+수동 그래프 조정이 섞여 있던 시절의 핫픽스였다. 지금은 AI 모드가 항상
        # 세부설정 UI 자체를 숨기고 매번 새로 해석하므로(커스텀 모드는 반대로 항상 honor=True,
        # 위 분기) 이 판정이 더 이상 필요 없다 — AI 모드는 항상 honor=False.
        # params.same_as_previous/payload.previous_prompt 자체는 하위호환을 위해 계속 받고
        # LLM에도 전달하지만(interpret 호출 그대로), 라우팅 판단에는 더 이상 쓰지 않는다.
        # 옛 판정식(참고용, 삭제 안 함): bool(payload.previous_prompt) and bool(params.same_as_previous)
        honor = False

        # ※ **스코프 필터(밴드·커버)는 honor와 무관하게 항상 적용** — 사용자가 명시적으로 좁힌 범위라
        #   프롬프트 mood와 독립적으로 지속되어야 한다(밴드 셀렉터가 2회차에 무시되던 문제 해소).

    # 커버/오리지널(스코프 필터): 프롬프트 의도와 무관하게 항상 사용자 명시값을 존중(없으면 LLM song_type).
    inc_original, inc_cover = _resolve_song_type(
        payload.include_original, payload.include_cover, params.song_type
    )
    songs = _apply_cover_filter(state.songs, inc_original, inc_cover)

    # 사용자 지정 단계(설정 §5-1a): honor일 때만 에너지 아크·곡 수를 강제(그래프 수동, 최대 11구간).
    stage_specs = None
    if honor and payload.stages:
        stage_specs = [
            StageSpec(
                energy_target=st.energy,
                song_count=st.song_count
                if st.song_count is not None
                else max(1, round(st.minutes * 60 / DEFAULT_AVG_SONG_SECONDS)),
                valence=st.valence,
                lufs_integrated=st.lufs_integrated,
                lra=st.lra,
                danceability_norm=st.danceability_norm,
                instr_stem_ratio=st.instr_stem_ratio,
                speech_median=st.speech_median,
                impression=st.impression,
                bands=tuple(st.bands) if st.bands else None,
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
        # AI 모드가 10~15분짜리 짧은 플리를 내놓던 버그(2026-08-11) 수정 — LLM이 target_minutes를
        # 너무 짧게 잡아도 여기서 최소 30분으로 다시 한번 하한을 강제한다(prompt.py의 LLM 지시문·
        # _MINUTES_RANGE와 동일한 하한을 이중으로 보장).
        minutes = max(30, min(_MAX_TARGET_MINUTES, minutes))

    effective = replace(params, stage_count=stage_count, target_minutes=minutes)
    # 프로토타입: 스테이지별 impression 텍스트(스펙 우선 → LLM 폴백, AI/커스텀 모드 공통 규칙)를
    # 임베딩(있을 때만) — 도메인은 임베딩 모델을 모르므로 조립 지점(라우트)에서 미리 벡터화해 넘긴다.
    stage_impression_texts = [
        resolve_stage_impression_text(i, stage_specs, effective) for i in range(effective.stage_count)
    ]
    stage_impression_vectors = _build_stage_impression_vectors(
        state.embedder, stage_impression_texts
    )
    setlist = build_setlist(
        songs, effective, target_seconds=minutes * 60,
        band_filter=band_filter, stage_specs=stage_specs,
        stage_impression_vectors=stage_impression_vectors,
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


@router.post("/api/setlist")
def create_setlist(payload: SetlistRequest, request: Request, response: Response) -> dict:
    # 응답 캐시 금지 — 매 요청 새로 생성되는 결과가 브라우저/프록시에 캐시돼 요약 카드가 '고착'되지
    # 않도록 방지(사용자 보고: 캐시 지우기 전까지 동일 요약 유지).
    response.headers["Cache-Control"] = "no-store"

    state = request.app.state
    estimate_fn = getattr(state.interpreter, "estimate_wait", None)
    if payload.mode == "custom" or estimate_fn is None:
        # 커스텀 모드(LLM 호출 없음)이거나, 인터프리터에 TPM 리미터가 없어(estimate_wait 미구현
        # — 스텁 어댑터·GROQ_TPM_LIMIT=0 등) 대기 가능성 자체가 없으면 그대로 동기 처리한다.
        # 폴링 왕복 지연을 더할 이유가 없는 경우까지 잡으로 밀 필요는 없다.
        return _run_setlist(payload, state)

    # AI 모드 + TPM 리미터 활성: interpreter.interpret()가 몇 분까지 대기할 수 있다(groq_adapter.py
    # tpm_max_wait). HTTP 요청 안에서 블로킹하면 플랫폼 프록시 타임아웃에 걸릴 수 있어(2026-08-10),
    # 잡으로 등록만 하고 즉시 202로 응답 — 프론트는 GET .../status/{job_id}로 폴링한다.
    band_names = {b.strip() for b in (payload.bands or []) if b and b.strip()}
    band_names |= detect_bands(payload.prompt or "")
    pool = [s for s in state.songs if not band_names or s.band in band_names]
    estimate = lambda: estimate_fn(payload.prompt, payload.previous_prompt, _feature_stats(pool))  # noqa: E731
    # 제출 "직전"에 한 번 재보고 응답에 그대로 싣는다 — job.estimated_wait_seconds()는 폴링용이라
    # 잡이 이미 끝났으면 0을 주는데(status="done"/"error"), 잡이 아주 빨리 끝나버리면(경합) 방금
    # 등록한 202 응답조차 그 로직을 타서 "얼마나 기다렸어야 했는지"가 뭉개지는 문제가 있었다.
    initial_wait = estimate()
    # QueueFullError(대기열 정원 초과)는 여기서 안 잡는다 — main.py의 전용 핸들러가 429로 매핑.
    job = state.job_store.submit(lambda: _run_setlist(payload, state), estimate=estimate)
    response.status_code = 202
    return {
        "job_id": job.id,
        "estimated_wait_seconds": None if initial_wait == float("inf") else round(initial_wait, 1),
        "queue_position": state.job_store.queue_position(job),
    }


@router.get("/api/setlist/status/{job_id}")
def get_setlist_status(job_id: str, response: Response, request: Request) -> dict:
    """POST /api/setlist(AI 모드)가 등록한 잡의 진행상황 폴링. 2~3초 간격 폴링을 전제로 가볍게 설계."""
    response.headers["Cache-Control"] = "no-store"
    job_store = request.app.state.job_store
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "JOB_NOT_FOUND", "message": "요청을 찾을 수 없습니다(만료됐을 수 있어요)."}}
        )
    if job.status == "done":
        return {"status": "done", "result": job.result}
    if job.status == "error":
        response.status_code = job.error["status_code"]
        return {"status": "error", "error": {"code": job.error["code"], "message": job.error["message"]}}
    return {
        "status": job.status,
        "estimated_wait_seconds": job.estimated_wait_seconds(),
        "queue_position": job_store.queue_position(job),
    }


@router.post("/api/admin/refresh-data")
def refresh_data(request: Request, x_refresh_token: str | None = Header(default=None)) -> dict:
    """`data` 브랜치 songs_master.csv를 즉시 재fetch — 오토로더가 push 직후 호출해서 백엔드가
    이미 깨어있는(웜) 상태일 때 DATA_REFRESH_INTERVAL_SEC(기본 30분) 대기 없이 신곡을 바로
    반영하기 위함. 백엔드가 잠들어 있으면 이 호출 자체가 콜드부팅을 유발해 어차피 최신 데이터를
    받아오므로 무해하다.

    DATA_REFRESH_TOKEN env가 설정돼 있어야 하고, 헤더 X-Refresh-Token이 정확히 일치해야 한다.
    env 미설정(기본, 로컬 개발)이면 이 엔드포인트는 항상 403이다 — 옵트인 전용 기능.
    """
    expected = os.environ.get("DATA_REFRESH_TOKEN", "").strip()
    provided = x_refresh_token or ""
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="forbidden")
    songs = request.app.state.refresh_songs(force=True)
    request.app.state.songs = songs
    return {"status": "ok", "song_count": len(songs)}
