"""Notifier 테스트 — best-effort·throttle 보장(실제 네트워크 호출 금지)."""

import asyncio

from app.adapters.telegram_notifier import TelegramNotifier
from app.ports.notify_port import NoopNotifier


def test_noop_notifier_is_silent():
    asyncio.run(NoopNotifier().notify("ERR", "detail"))  # 예외 없이 통과


def test_telegram_throttles_same_title():
    n = TelegramNotifier("t", "c", throttle_seconds=1000)
    sent = []

    async def fake_send(text):
        sent.append(text)

    n._send = fake_send
    asyncio.run(n.notify("ERR", "a"))
    asyncio.run(n.notify("ERR", "b"))     # 같은 title → throttle로 스킵
    asyncio.run(n.notify("OTHER", "c"))   # 다른 title → 전송
    assert len(sent) == 2


def test_telegram_swallows_send_error():
    n = TelegramNotifier("t", "c")

    async def boom(text):
        raise RuntimeError("net down")

    n._send = boom
    asyncio.run(n.notify("ERR", "d"))  # 예외가 밖으로 새지 않아야 함
