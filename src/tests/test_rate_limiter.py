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


def test_variable_cost_consumes_proportionally():
    """TPM 페이싱용 사용법: cost로 실제 토큰량을 넘기면 그만큼 소비한다(RPM처럼 항상 1이 아님)."""
    lim = TokenBucketLimiter(rate_per_min=8000, burst=8000, max_wait=0, max_waiters=0)
    assert lim.acquire(cost=5000) is True
    assert lim.acquire(cost=5000) is False  # 남은 3000으로는 부족 → 즉시 거절(대기 불가 설정)
    assert lim.acquire(cost=3000) is True  # 남은 예산만큼은 통과


def test_cost_exceeding_capacity_never_succeeds():
    """추정 비용이 버킷 용량 자체보다 크면 아무리 기다려도 못 채우므로 즉시 거절."""
    lim = TokenBucketLimiter(rate_per_min=8000, burst=8000, max_wait=5.0, max_waiters=5)
    assert lim.acquire(cost=9000) is False
