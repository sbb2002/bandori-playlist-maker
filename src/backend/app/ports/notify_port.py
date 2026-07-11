"""Notifier 포트 — 운영 중 오류를 개발자 채널로 알림(트래픽 급증·런타임 에러 대비).

도메인/API는 이 인터페이스만 안다. 구현(Telegram 등)은 `adapters/` 하위 단일 파일이며
main.py에서 주입한다. 알림은 항상 **best-effort** — 실패하거나 미설정이어도 요청/에러 처리에
영향을 주지 않아야 한다(NoopNotifier가 기본 폴백).
"""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    """오류 알림 포트. 구현은 벤더별 단일 어댑터(Telegram 등)."""

    async def notify(self, title: str, body: str) -> None:
        """개발자 채널로 알림(비차단·best-effort). 예외를 밖으로 던지지 않는다."""
        ...


class NoopNotifier:
    """미설정 기본값 — 아무것도 하지 않음(로컬/토큰 없음일 때)."""

    async def notify(self, title: str, body: str) -> None:
        return None
