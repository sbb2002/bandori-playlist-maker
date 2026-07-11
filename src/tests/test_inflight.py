"""InflightLimitMiddleware — 상한 초과 거절(503) / 정상 통과 카운트."""

import asyncio

from app.main import InflightLimitMiddleware


def _run(mw, scope):
    sent = []

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {}

    asyncio.run(mw(scope, receive, send))
    return sent


def test_rejects_when_queue_full():
    calls = []

    async def inner(scope, receive, send):
        calls.append(1)

    mw = InflightLimitMiddleware(inner, limit=2)
    mw.count = 2  # 가득
    sent = _run(mw, {"type": "http", "path": "/api/setlist", "app": None})

    assert not calls  # 내부 앱 미호출
    assert sent[0]["status"] == 503
    body = sent[1]["body"].decode("utf-8")
    assert "너무 많아요" in body


def test_passes_through_and_decrements():
    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["path"])

    mw = InflightLimitMiddleware(inner, limit=2)
    _run(mw, {"type": "http", "path": "/api/setlist", "app": None})

    assert calls == ["/api/setlist"]
    assert mw.count == 0  # 처리 후 감소


def test_ignores_other_paths():
    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["path"])

    mw = InflightLimitMiddleware(inner, limit=1)
    mw.count = 5  # 가득이지만 다른 경로는 제한 대상 아님
    _run(mw, {"type": "http", "path": "/api/health", "app": None})

    assert calls == ["/api/health"]  # 통과(카운트 무관)
