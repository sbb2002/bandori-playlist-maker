"""Telegram 알림 어댑터 — 운영 오류를 봇 메시지로 전송(Notifier 포트 구현).

설정(시크릿): TELEGRAM_BOT_TOKEN(@BotFather 발급) + TELEGRAM_CHAT_ID(본인 chat id).
- best-effort: 전송 실패는 삼켜서 요청/에러 처리를 깨지 않는다.
- throttle: 같은 title은 창(기본 5분) 내 1회만 — 에러 폭주 시 스팸 방지.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger("setlist_maker")


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        throttle_seconds: float = 300.0,
        timeout: float = 5.0,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._throttle = max(0.0, throttle_seconds)
        self._timeout = timeout
        self._recent: dict[str, float] = {}  # title -> 마지막 전송 시각(monotonic)

    async def notify(self, title: str, body: str) -> None:
        try:
            now = time.monotonic()
            last = self._recent.get(title)
            if last is not None and now - last < self._throttle:
                return  # 같은 유형 에러 스팸 방지
            self._recent[title] = now
            await self._send(f"⚠️ setlist-maker\n{title}\n{body}"[:3900])
        except Exception:  # noqa: BLE001 — 알림 실패가 요청/에러 처리를 깨면 안 됨
            logger.warning("Telegram 알림 전송 실패(무시)", exc_info=True)

    async def _send(self, text: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await client.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
            )
