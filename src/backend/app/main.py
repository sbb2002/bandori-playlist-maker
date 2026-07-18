"""FastAPI 앱 생성 + composition root.

여기서만 어댑터를 포트 자리에 주입한다(도메인·API는 구현을 모른다). CORS·예외 핸들러·
라우터 등록을 담당. 벤더 교체 = 아래 `_build_interpreter()` 주입 1지점 교체.

주요 환경변수:
    GROQ_API_KEY         있으면 Groq 어댑터, 없으면 스텁(오프라인) 어댑터 사용.
    GROQ_MODEL           모델 ID override(기본: groq_adapter.DEFAULT_MODEL).
    GROQ_BASE_URL        베이스 URL override.
    GROQ_MAX_RETRIES     429/5xx 백오프 재시도 횟수(기본 2).
    GROQ_MOOD_RETRIES    200 응답인데 content가 무드 JSON으로 파싱 안 될 때 재호출 횟수(기본 3,
                         디테일한 다단계 절대시간 요청에서 간헐적 파싱 실패 완화).
    MOOD_INTERPRETER     "stub" | "groq" 로 강제 선택(기본: 키 유무로 자동).
    FRONTEND_ORIGIN      CORS 허용 오리진(쉼표 구분). 개발용 localhost는 항상 허용.
    TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID   운영 오류 Telegram 알림(선택, 둘 다 필요).
    SONGS_CSV            songs_master.csv 경로 override(설정 시 `data` 브랜치 원격 fetch를 건너뜀).
    DATA_REFRESH_INTERVAL_SEC   `data` 브랜치 재fetch 주기(초, 기본 1800=30분). 0=주기 리프레시 비활성
                                (기동 시 최초 1회만 로드).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
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
from .repo import remote_source
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


def _compute_version() -> str:
    """현재 커밋 SHA(짧은형). Render는 RENDER_GIT_COMMIT, 로컬은 git, 둘 다 없으면 'dev'.

    프론트 우하단 버전 표기에 노출(/api/health). 배포 프론트는 빌드시 SHA를 직접 주입하지만,
    로컬·주입 실패 시 이 값을 폴백으로 쓴다.
    """
    sha = os.environ.get("RENDER_GIT_COMMIT", "").strip()
    if sha:
        return sha[:7]
    try:
        import subprocess

        root = Path(__file__).resolve().parents[3]  # repo root
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root), stderr=subprocess.DEVNULL, timeout=2,
        )
        return out.decode().strip() or "dev"
    except Exception:  # noqa: BLE001 — git 미존재/오류 시 폴백
        return "dev"


def _build_interpreter() -> MoodInterpreter:
    """환경에 따라 MoodInterpreter 구현을 선택한다(composition root 주입 지점).

    OpenRouter 키가 있으면 운영 어댑터, 없으면 스텁 어댑터(오프라인 구동 검증용).
    """
    mode = os.environ.get("MOOD_INTERPRETER", "").strip().lower()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    use_llm = mode in ("groq", "openrouter", "groq_multistage") or (mode != "stub" and bool(api_key))

    if use_llm and mode == "groq_multistage":
        # (실험, topic/llm-param-control-separate) 파라미터마다 순차 LLM 호출로 나눠 JSON을
        # 조립하는 파일럿 어댑터. 벤더 어댑터 자체를 통째로 교체하는 실험이라 groq_adapter와
        # 별도 분기로 둔다 — 운영 분기(아래)에는 영향 없음.
        if not api_key:
            raise RuntimeError("MOOD_INTERPRETER=groq_multistage인데 GROQ_API_KEY가 없습니다.")

        from .adapters.groq_multistage_adapter import (
            DEFAULT_BASE_URL as MS_DEFAULT_BASE_URL,
            DEFAULT_MODEL as MS_DEFAULT_MODEL,
            GroqMultistageMoodInterpreter,
        )

        model = os.environ.get("GROQ_MODEL", MS_DEFAULT_MODEL)
        base_url = os.environ.get("GROQ_BASE_URL", MS_DEFAULT_BASE_URL)
        max_retries = _env_int("GROQ_MAX_RETRIES", 2)
        stage_retries = _env_int("GROQ_MOOD_RETRIES", 2)
        logger.info(
            "MoodInterpreter: GroqMultistage (실험, model=%s, stage_retries=%s)",
            model, stage_retries,
        )
        return GroqMultistageMoodInterpreter(
            api_key=api_key, model=model, base_url=base_url,
            max_retries=max_retries, stage_retries=stage_retries,
        )

    if use_llm:
        if not api_key:
            raise RuntimeError("MOOD_INTERPRETER로 LLM을 강제했지만 GROQ_API_KEY가 없습니다.")

        # (Groq 어댑터) GroqMoodInterpreter를 주입. 벤더 교체 시 이 import·클래스만 바꾸면 된다.
        from .adapters.groq_adapter import DEFAULT_BASE_URL, DEFAULT_MODEL, GroqMoodInterpreter

        model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        base_url = os.environ.get("GROQ_BASE_URL", DEFAULT_BASE_URL)
        referer = os.environ.get("FRONTEND_ORIGIN", "").split(",")[0].strip() or None
        response_format = os.environ.get("GROQ_RESPONSE_FORMAT", "none")
        max_retries = _env_int("GROQ_MAX_RETRIES", 2)  # 트래픽 급증 시 429 백오프 재시도 횟수
        mood_parse_retries = _env_int("GROQ_MOOD_RETRIES", 3)  # 무드 파싱 실패 시 재호출 횟수
        rate_per_min = _env_int("GROQ_RATE_PER_MIN", 25)  # 프로액티브 RPM 준수(0=비활성)
        logger.info(
            "MoodInterpreter: Groq (model=%s, response_format=%s, rate_per_min=%s, mood_parse_retries=%s)",
            model, response_format, rate_per_min, mood_parse_retries,
        )
        return GroqMoodInterpreter(
            api_key=api_key, model=model, base_url=base_url, referer=referer,
            response_format_mode=response_format, max_retries=max_retries,
            mood_parse_retries=mood_parse_retries,
            rate_per_min=rate_per_min,
        )

    from .adapters.stub_adapter import StubMoodInterpreter

    logger.warning(
        "MoodInterpreter: STUB (오프라인 휴리스틱). GROQ_API_KEY 설정 시 Groq로 자동 전환."
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


class InflightLimitMiddleware:
    """/api/setlist 동시 처리 수를 상한(REQUEST_QUEUE_MAX, 기본 200)으로 제한하는 ASGI 미들웨어.

    스레드를 붙잡지 않고 이벤트 루프에서 in-flight 수를 카운트한다(단일 스레드라 락 불필요).
    상한 초과 시 즉시 503 안내 + 개발자 알림(best-effort, 스로틀). CORS 헤더 유지를 위해
    CORS 미들웨어 '안쪽'에 둔다(create_app에서 CORS보다 먼저 add → CORS가 바깥).
    """

    def __init__(self, app, limit: int = 200, path_prefix: str = "/api/setlist") -> None:
        self.app = app
        self.limit = max(1, limit)
        self.path_prefix = path_prefix
        self.count = 0

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not scope.get("path", "").startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return
        if self.count >= self.limit:
            self._alert_overload(scope)
            await self._reject(send)
            return
        self.count += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.count -= 1

    def _alert_overload(self, scope) -> None:
        app = scope.get("app")
        notifier = getattr(getattr(app, "state", None), "notifier", None)
        if notifier is None:
            return
        try:
            task = asyncio.create_task(
                notifier.notify("OVERLOADED 503", f"동시 요청 상한({self.limit}) 초과 — 큐 가득")
            )
        except RuntimeError:
            return
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    async def _reject(self, send) -> None:
        payload = {"error": {"code": "OVERLOADED",
                             "message": "요청이 너무 많아요 ㅠㅠ 나중에 다시 이용해주세요!"}}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _load_current_songs(*, force: bool = False) -> list:
    """`data` 브랜치에서 songs_master.csv를 fetch(또는 캐시 재사용)해 적재한다."""
    path = remote_source.ensure_songs_csv(force=force)
    return load_songs(path)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """기동 후 주기적으로 `data` 브랜치를 재fetch해 `app.state.songs`를 갱신한다.

    `main` 재배포 없이 신곡이 반영되게 하는 것이 목적(data 브랜치는 main에 병합되지 않음 —
    git-rules.md). DATA_REFRESH_INTERVAL_SEC=0이면 이 루프를 비활성화(기동 시 1회 로드만).
    리프레시 실패는 기존 `app.state.songs`를 그대로 유지하고 다음 주기에 재시도한다.
    """
    interval = _env_int("DATA_REFRESH_INTERVAL_SEC", 1800)
    task: asyncio.Task | None = None
    if interval > 0:
        async def _refresh_loop() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    songs = await asyncio.to_thread(_load_current_songs, force=True)
                except Exception:  # noqa: BLE001 — 리프레시 실패는 기존 데이터로 계속 서빙
                    logger.warning("songs_master.csv 주기 리프레시 실패(기존 데이터 유지).", exc_info=True)
                    continue
                app.state.songs = songs
                logger.info("곡 %d건 주기 리프레시 완료.", len(songs))

        task = asyncio.create_task(_refresh_loop())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


def create_app() -> FastAPI:
    _load_dotenv()  # 어댑터·CORS가 env를 읽기 전에 .env 주입.
    app = FastAPI(title="setlist-maker", version="0.1.0-pilot", lifespan=_lifespan)

    # 입장제어(in-flight 상한) — CORS보다 먼저 add해 CORS가 바깥에서 감싸도록(거절 응답에도 CORS 헤더).
    app.add_middleware(InflightLimitMiddleware, limit=_env_int("REQUEST_QUEUE_MAX", 200))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),  # 와일드카드 금지(backend/README §7)
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # composition root: 어댑터·데이터를 app.state에 주입.
    app.state.version = _compute_version()
    app.state.interpreter = _build_interpreter()
    app.state.interpreter_name = type(app.state.interpreter).__name__  # /api/health 진단(stub|groq 확인)
    app.state.notifier = _build_notifier()
    app.state.songs = _load_current_songs()
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
