"""FastAPI 앱 생성 + composition root.

여기서만 어댑터를 포트 자리에 주입한다(도메인·API는 구현을 모른다). CORS·예외 핸들러·
라우터 등록을 담당. 벤더 교체 = 아래 `_build_interpreter()` 주입 1지점 교체.

주요 환경변수:
    (OPENROUTER 사용 시)
    GroqGROQ_API_KEY   있으면 OpenRouter 어댑터, 없으면 스텁(오프라인) 어댑터 사용.
    OPENROUTER_MODEL     모델 ID override.
    OPENROUTER_BASE_URL  베이스 URL override.

    (GROQ 사용 시)
    GROQ_API_KEY         Groq API 키.
    GROQ_MODEL           모델 ID override.
    GROQ_BASE_URL        베이스 URL override.

    (공통)
    MOOD_INTERPRETER     "stub" | "openrouter" | "groq" 로 강제 선택(기본: 키 유무로 자동).
    FRONTEND_ORIGIN      CORS 허용 오리진(쉼표 구분). 개발용 localhost는 항상 허용.
    SONGS_CSV            songs_master.csv 경로 override.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .domain.models import NoSetlistError
from .ports.mood_port import (
    LLMRateLimitError,
    LLMUpstreamError,
    MoodInterpretationError,
    MoodInterpreter,
)
from .ports.notify_port import Notifier, NoopNotifier
from .repo.song_repo import load_songs

logger = logging.getLogger("setlist_maker")

# 백그라운드 알림 태스크 참조 보관(조기 GC 방지 — asyncio.create_task 관례).
_bg_tasks: set[asyncio.Task] = set()

# 개발 편의를 위해 항상 허용하는 로컬 오리진(정적 프론트 로컬 서빙).
_DEV_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _load_dotenv() -> None:
    """의존성 없이 .env를 읽어 os.environ에 주입한다(이미 설정된 값은 유지).

    탐색 위치: 리포지토리 루트 `.env`, `src/backend/.env`. 시크릿 파일이므로 커밋 금지
    (.gitignore가 `.env` 차단). 예시는 `src/backend/.env.example` 참조.
    """
    here = Path(__file__).resolve()
    candidates = [here.parents[3] / ".env", here.parents[1] / ".env"]  # repo root, src/backend
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """스키마3 공통 에러 포맷."""
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _cors_origins() -> list[str]:
    configured = os.environ.get("FRONTEND_ORIGIN", "")
    origins = [o.strip() for o in configured.split(",") if o.strip()]
    return origins + _DEV_ORIGINS


def _env_int(key: str, default: int) -> int:
    """정수 환경변수 안전 파싱(비어있거나 잘못되면 기본값)."""
    try:
        return int(os.environ.get(key, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _build_interpreter() -> MoodInterpreter:
    """환경에 따라 MoodInterpreter 구현을 선택한다(composition root 주입 지점).

    OpenRouter 키가 있으면 운영 어댑터, 없으면 스텁 어댑터(오프라인 구동 검증용).
    """
    mode = os.environ.get("MOOD_INTERPRETER", "").strip().lower()
    api_key = os.environ.get("GroqGROQ_API_KEY", "").strip()

    use_openrouter = mode == "openrouter" or (mode != "stub" and bool(api_key))

    if use_openrouter:
        if not api_key:
            raise RuntimeError("MOOD_INTERPRETER=openrouter 인데 GroqGROQ_API_KEY가 없습니다.")
        
        # (OpenRouter 어댑터) OpenRouterMoodInterpreter를 주입.
        # from .adapters.openrouter_adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenRouterMoodInterpreter

        # (Groq 어댑터) GroqMoodInterpreter를 주입.
        from .adapters.groq_adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, GroqMoodInterpreter

        MoodInterpreterClass = GroqMoodInterpreter  # OpenRouterMoodInterpreter

        MODEL = "GROQ_MODEL"  # OpenRouter: "OPENROUTER_MODEL"
        BASE_URL = "GROQ_BASE_URL"  # OpenRouter: "OPENRO

        model = os.environ.get(MODEL, DEFAULT_MODEL)
        base_url = os.environ.get(BASE_URL, DEFAULT_BASE_URL)
        referer = os.environ.get("FRONTEND_ORIGIN", "").split(",")[0].strip() or None
        response_format = os.environ.get("GROQ_RESPONSE_FORMAT", "none")
        max_retries = _env_int("GROQ_MAX_RETRIES", 2)  # 트래픽 급증 시 429 백오프 재시도 횟수
        logger.info("MoodInterpreter: Groq (model=%s, response_format=%s)", model, response_format)
        return MoodInterpreterClass(
            api_key=api_key, model=model, base_url=base_url, referer=referer,
            response_format_mode=response_format, max_retries=max_retries,
        )

    from .adapters.stub_adapter import StubMoodInterpreter

    logger.warning(
        "MoodInterpreter: STUB (오프라인 휴리스틱). GroqGROQ_API_KEY 설정 시 OpenRouter로 자동 전환."
    )
    return StubMoodInterpreter()


def _build_notifier() -> Notifier:
    """오류 알림 채널 선택(composition root). Telegram 자격증명 있으면 Telegram, 없으면 Noop.

    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID(둘 다) 설정 시 활성. 시크릿이므로 커밋 금지.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        from .adapters.telegram_notifier import TelegramNotifier

        logger.info("Notifier: Telegram (운영 오류 알림 활성)")
        return TelegramNotifier(token, chat_id)

    logger.info("Notifier: Noop (TELEGRAM_BOT_TOKEN/CHAT_ID 미설정 — 알림 비활성)")
    return NoopNotifier()


def _alert(request: Request, title: str, exc: Exception) -> None:
    """개발자 채널로 오류 알림을 비차단 예약(best-effort). 실패해도 응답에 영향 없음."""
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is None:
        return
    body = f"{request.method} {request.url.path}\n{type(exc).__name__}: {exc}"[:1500]
    try:
        task = asyncio.create_task(notifier.notify(title, body))
    except RuntimeError:
        return  # 러닝 루프 없음(이론상 없음) — 무시
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def create_app() -> FastAPI:
    _load_dotenv()  # 어댑터·CORS가 env를 읽기 전에 .env 주입.
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
    app.state.notifier = _build_notifier()
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

    @app.exception_handler(LLMRateLimitError)
    async def _on_ratelimit(_: Request, exc: LLMRateLimitError) -> JSONResponse:
        # 트래픽 급증: 재시도 소진 후에도 429 → 친절한 안내(프론트가 그대로 표시).
        return _error_response(429, "RATE_LIMITED", "지금 요청이 많아요. 잠시 후 다시 시도해 주세요. 🙏")

    @app.exception_handler(LLMUpstreamError)
    async def _on_upstream(request: Request, exc: LLMUpstreamError) -> JSONResponse:
        _alert(request, "LLM_UPSTREAM 502", exc)
        return _error_response(502, "LLM_UPSTREAM_FAILED", "LLM 호출에 실패했습니다. 잠시 후 다시 시도하세요.")

    @app.exception_handler(NoSetlistError)
    async def _on_no_setlist(_: Request, exc: NoSetlistError) -> JSONResponse:
        return _error_response(409, "NO_SETLIST", "조건에 맞는 세트리스트를 만들 수 없습니다.")

    @app.exception_handler(Exception)
    async def _on_internal(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 오류: %s", exc)
        _alert(request, "INTERNAL 500", exc)
        return _error_response(500, "INTERNAL", "서버 내부 오류가 발생했습니다.")


# uvicorn src.backend.app.main:app 진입점.
app = create_app()
