"""FastAPI 앱 생성 + composition root.

여기서만 어댑터를 포트 자리에 주입한다(도메인·API는 구현을 모른다). CORS·예외 핸들러·
라우터 등록을 담당. 벤더 교체 = 아래 `_build_interpreter()` 주입 1지점 교체.

주요 환경변수:
    OPENROUTER_API_KEY   있으면 OpenRouter 어댑터, 없으면 스텁(오프라인) 어댑터 사용.
    MOOD_INTERPRETER     "stub" | "openrouter" 로 강제 선택(기본: 키 유무로 자동).
    OPENROUTER_MODEL     모델 ID override.
    OPENROUTER_BASE_URL  베이스 URL override.
    FRONTEND_ORIGIN      CORS 허용 오리진(쉼표 구분). 개발용 localhost는 항상 허용.
    SONGS_CSV            songs_master.csv 경로 override.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .domain.models import NoSetlistError
from .ports.mood_port import (
    LLMUpstreamError,
    MoodInterpretationError,
    MoodInterpreter,
)
from .repo.song_repo import load_songs

logger = logging.getLogger("setlist_maker")

# 개발 편의를 위해 항상 허용하는 로컬 오리진(정적 프론트 로컬 서빙).
_DEV_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """스키마3 공통 에러 포맷."""
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _cors_origins() -> list[str]:
    configured = os.environ.get("FRONTEND_ORIGIN", "")
    origins = [o.strip() for o in configured.split(",") if o.strip()]
    return origins + _DEV_ORIGINS


def _build_interpreter() -> MoodInterpreter:
    """환경에 따라 MoodInterpreter 구현을 선택한다(composition root 주입 지점).

    OpenRouter 키가 있으면 운영 어댑터, 없으면 스텁 어댑터(오프라인 구동 검증용).
    """
    mode = os.environ.get("MOOD_INTERPRETER", "").strip().lower()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    use_openrouter = mode == "openrouter" or (mode != "stub" and bool(api_key))

    if use_openrouter:
        if not api_key:
            raise RuntimeError("MOOD_INTERPRETER=openrouter 인데 OPENROUTER_API_KEY가 없습니다.")
        from .adapters.openrouter_adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenRouterMoodInterpreter

        model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        base_url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
        referer = os.environ.get("FRONTEND_ORIGIN", "").split(",")[0].strip() or None
        logger.info("MoodInterpreter: OpenRouter (model=%s)", model)
        return OpenRouterMoodInterpreter(api_key=api_key, model=model, base_url=base_url, referer=referer)

    from .adapters.stub_adapter import StubMoodInterpreter

    logger.warning(
        "MoodInterpreter: STUB (오프라인 휴리스틱). OPENROUTER_API_KEY 설정 시 OpenRouter로 자동 전환."
    )
    return StubMoodInterpreter()


def create_app() -> FastAPI:
    app = FastAPI(title="setlist-maker", version="0.1.0-pilot")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),  # 와일드카드 금지(backend/README §7)
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # composition root: 어댑터·데이터를 app.state에 주입.
    app.state.interpreter = _build_interpreter()
    app.state.songs = load_songs()
    logger.info("곡 %d건 적재 완료.", len(app.state.songs))

    app.include_router(router)
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(400, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.")

    @app.exception_handler(MoodInterpretationError)
    async def _on_mood(_: Request, exc: MoodInterpretationError) -> JSONResponse:
        return _error_response(422, "MOOD_UNINTERPRETABLE", "요청을 무드로 해석하지 못했습니다.")

    @app.exception_handler(LLMUpstreamError)
    async def _on_upstream(_: Request, exc: LLMUpstreamError) -> JSONResponse:
        return _error_response(502, "LLM_UPSTREAM_FAILED", "LLM 호출에 실패했습니다. 잠시 후 다시 시도하세요.")

    @app.exception_handler(NoSetlistError)
    async def _on_no_setlist(_: Request, exc: NoSetlistError) -> JSONResponse:
        return _error_response(409, "NO_SETLIST", "조건에 맞는 세트리스트를 만들 수 없습니다.")

    @app.exception_handler(Exception)
    async def _on_internal(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 오류: %s", exc)
        return _error_response(500, "INTERNAL", "서버 내부 오류가 발생했습니다.")


# uvicorn src.backend.app.main:app 진입점.
app = create_app()
