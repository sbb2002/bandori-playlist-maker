"""API 라우트 — POST /api/setlist, GET /api/health.

어댑터·데이터는 request.app.state에서 꺼내 쓴다(주입은 main.py). 도메인 에러는 여기서
잡지 않고 그대로 전파하여 main.py의 예외 핸들러가 스키마3 에러 포맷으로 매핑한다.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request

from ..domain.models import MoodParameters
from ..domain.selection import build_setlist
from .schemas import SetlistRequest, serialize_setlist

router = APIRouter()

_DEFAULT_TARGET_MINUTES = 60


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/api/setlist")
def create_setlist(payload: SetlistRequest, request: Request) -> dict:
    interpreter = request.app.state.interpreter
    songs = request.app.state.songs

    params: MoodParameters = interpreter.interpret(payload.prompt)

    # 요청이 명시한 값은 LLM 해석을 override(architecture.md 스키마3).
    stage_count = payload.stage_count if payload.stage_count is not None else params.stage_count
    stage_count = max(2, min(5, stage_count))

    minutes = payload.target_minutes if payload.target_minutes is not None else params.target_minutes
    if minutes is None:
        minutes = _DEFAULT_TARGET_MINUTES
    minutes = max(10, min(180, minutes))

    effective = replace(params, stage_count=stage_count, target_minutes=minutes)
    setlist = build_setlist(songs, effective, target_seconds=minutes * 60)
    return serialize_setlist(setlist)
