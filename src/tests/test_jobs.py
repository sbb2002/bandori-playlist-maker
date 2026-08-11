"""JobStore 단위 테스트 — 정원(max_queue_len) 거절, queue_position 계산, 잡 실행/에러 매핑.

test_setlist_queue.py가 HTTP 계약(202/폴링 응답 모양)을 다룬다면, 이 파일은 JobStore
자체의 동작(락 밑 로직)을 HTTP 없이 직접 검증한다.
"""

import threading
import time

import pytest

from app.api.errors import QueueFullError
from app.jobs import JobStore


def test_submit_runs_job_and_reports_done():
    store = JobStore(max_workers=4, max_queue_len=4)
    job = store.submit(lambda: {"ok": True})
    _wait_until(lambda: store.get(job.id).status in ("done", "error"))
    fetched = store.get(job.id)
    assert fetched.status == "done"
    assert fetched.result == {"ok": True}


def test_submit_maps_exception_to_job_error():
    store = JobStore(max_workers=4, max_queue_len=4)

    def boom():
        raise ValueError("kaboom")

    job = store.submit(boom)
    _wait_until(lambda: store.get(job.id).status in ("done", "error"))
    fetched = store.get(job.id)
    assert fetched.status == "error"
    assert fetched.error["status_code"] == 500  # map_error()의 알 수 없는 예외 폴백


def test_queue_full_rejects_beyond_max_queue_len():
    # 워커를 막아 잡들이 계속 running 상태로 남게 해서 정원 로직을 재현한다.
    release = threading.Event()

    def blocking():
        release.wait(timeout=5)
        return {"ok": True}

    store = JobStore(max_workers=2, max_queue_len=2)
    job1 = store.submit(blocking)
    job2 = store.submit(blocking)
    with pytest.raises(QueueFullError):
        store.submit(blocking)  # 정원(2) 초과 — 즉시 거절, 실행조차 안 됨
    release.set()
    _wait_until(lambda: store.get(job1.id).status == "done")
    _wait_until(lambda: store.get(job2.id).status == "done")


def test_queue_position_counts_only_earlier_unfinished_jobs():
    release = threading.Event()

    def blocking():
        release.wait(timeout=5)
        return {"ok": True}

    store = JobStore(max_workers=1, max_queue_len=10)  # 워커 1개 → 뒤에 들어온 잡은 확실히 대기
    job1 = store.submit(blocking)
    job2 = store.submit(blocking)
    job3 = store.submit(blocking)

    _wait_until(lambda: store.get(job1.id).status == "running")
    # job1이 워커를 붙잡고 있는 동안 job2/job3는 아직 queued — 앞서 들어온 미완료 잡 수를 정확히 세야 한다.
    assert store.queue_position(job2) == 1  # job1만 앞서 있고 아직 안 끝남
    assert store.queue_position(job3) == 2  # job1·job2 둘 다 앞서 있고 안 끝남
    assert store.queue_position(job1) == 0  # 내가 제일 먼저 — 앞에 아무도 없음

    release.set()
    _wait_until(lambda: store.get(job3.id).status == "done")
    assert store.queue_position(job2) == 0  # 다 끝나면 0
    assert store.queue_position(job3) == 0


def _wait_until(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.02)
    raise TimeoutError("조건이 제시간 안에 참이 되지 않음")
