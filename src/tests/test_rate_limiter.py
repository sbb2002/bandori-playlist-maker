"""TokenBucketLimiter 테스트 — 버스트 허용·대기열 거절·충전 후 재허용."""

from app.adapters.rate_limiter import TokenBucketLimiter


def test_burst_allows_immediate_then_rejects():
    lim = TokenBucketLimiter(rate_per_min=1, burst=3, max_wait=0, max_waiters=0)
    assert lim.acquire() is True
    assert lim.acquire() is True
    assert lim.acquire() is True
    assert lim.acquire() is False  # 버스트 소진 + 충전 느림·대기 불가 → 거절


def test_rejects_when_queue_full():
    lim = TokenBucketLimiter(rate_per_min=1, burst=1, max_wait=5, max_waiters=0)
    assert lim.acquire() is True
    assert lim.acquire() is False  # 토큰 없음 + 대기열(0) → 즉시 거절


def test_refill_after_short_wait():
    lim = TokenBucketLimiter(rate_per_min=6000, burst=1, max_wait=1.0, max_waiters=5)  # 100/s
    assert lim.acquire() is True
    assert lim.acquire() is True  # ~10ms 후 충전되어 성공(대기 경로)
