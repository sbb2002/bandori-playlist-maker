"""토큰버킷 레이트 리미터 — 벤더 RPM(분당 요청) 준수용 프로액티브 큐 제어.

동기 스레드풀 환경에서 LLM 호출을 페이싱한다(429를 사후 재시도만 하지 않고, 미리 속도를 제어).
`acquire()`는 토큰이 있으면 즉시 True, 없으면 대기하되:
- 대기 예상이 max_wait를 넘으면 False(→ 호출측이 429로 매핑),
- 이미 대기 중인 요청이 max_waiters면 즉시 False(스레드풀 고갈·무한대기 방지).
"""

from __future__ import annotations

import threading
import time


class TokenBucketLimiter:
    """분당 rate_per_min개로 충전되는 토큰버킷(burst 만큼 순간 허용)."""

    def __init__(
        self,
        rate_per_min: float,
        burst: int | None = None,
        max_wait: float = 20.0,
        max_waiters: int = 20,
    ) -> None:
        self._rate = max(1e-4, rate_per_min / 60.0)  # 초당 토큰
        self._capacity = float(burst if burst is not None else max(1, int(rate_per_min)))
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._max_wait = max(0.0, max_wait)
        self._max_waiters = max(0, max_waiters)
        self._waiters = 0
        self._lock = threading.Lock()

    def _refill_locked(self) -> None:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now

    def acquire(self) -> bool:
        """토큰 1개 소비. 성공 True, 대기열 초과/과대기로 거절 시 False."""
        with self._lock:
            self._refill_locked()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            if self._waiters >= self._max_waiters:
                return False  # 큐 가득 — 즉시 거절
            self._waiters += 1

        try:
            deadline = time.monotonic() + self._max_wait
            while True:
                with self._lock:
                    self._refill_locked()
                    if self._tokens >= 1:
                        self._tokens -= 1
                        return True
                    need = (1.0 - self._tokens) / self._rate
                if time.monotonic() + need > deadline:
                    return False  # 너무 오래 기다려야 함 — 거절
                time.sleep(min(need, 0.5))
        finally:
            with self._lock:
                self._waiters -= 1
