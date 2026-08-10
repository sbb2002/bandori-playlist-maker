"""AI 모드 202(잡 등록)+폴링 계약 테스트 — 인터프리터가 estimate_wait를 구현할 때만
create_setlist가 비동기 경로로 빠진다(test_api.py의 stub은 estimate_wait가 없어 여전히
동기 200 — 그쪽은 이 파일이 건드리지 않는다).
"""

import os
import threading
import time

os.environ["MOOD_INTERPRETER"] = "stub"  # create_app 임포트 전에 오프라인 강제(실제론 아래서 교체)

import pytest
from fastapi.testclient import TestClient

from app.domain.models import MoodParameters
from app.main import create_app
from app.ports.mood_port import LLMRateLimitError


class _BlockingQueuedInterpreter:
    """queue_position/QueueFullError 테스트용 — release() 부를 때까지 interpret()가 안 끝난다."""

    def __init__(self):
        self._release = threading.Event()

    def estimate_wait(self, prompt, previous_prompt=None, feature_stats=None):
        return 0.0

    def interpret(self, prompt, previous_prompt=None, energy_stats=None, feature_stats=None):
        self._release.wait(timeout=5)
        return MoodParameters(
            brightness=0.5, start_energy=0.4, end_energy=0.4, stage_count=2,
            target_minutes=20, interpretation_summary="test",
        )

    def release(self):
        self._release.set()


class _FakeQueuedInterpreter:
    """interpret()·estimate_wait() 둘 다 구현 — TPM 리미터가 있는 GroqMoodInterpreter 흉내."""

    def __init__(self, wait_seconds=0.0, raise_exc=None):
        self._wait_seconds = wait_seconds
        self._raise_exc = raise_exc

    def estimate_wait(self, prompt, previous_prompt=None, feature_stats=None):
        return self._wait_seconds

    def interpret(self, prompt, previous_prompt=None, energy_stats=None, feature_stats=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        return MoodParameters(
            brightness=0.5, start_energy=0.4, end_energy=0.4, stage_count=2,
            target_minutes=20, interpretation_summary="test",
        )


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def _poll_until_terminal(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/setlist/status/{job_id}")
        if r.json()["status"] in ("done", "error"):
            return r
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} 이 {timeout}s 안에 끝나지 않음")


def test_ai_mode_with_estimator_returns_202_and_job_id(client):
    client.app.state.interpreter = _FakeQueuedInterpreter()
    r = client.post("/api/setlist", json={"prompt": "신나는 한 시간"})
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body and body["job_id"]
    assert body["estimated_wait_seconds"] == 0.0


def test_polling_reaches_done_with_result(client):
    client.app.state.interpreter = _FakeQueuedInterpreter()
    job_id = client.post("/api/setlist", json={"prompt": "신나는 한 시간"}).json()["job_id"]
    r = _poll_until_terminal(client, job_id)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["picks"], "picks가 비어 있으면 안 됨"


def test_polling_surfaces_mapped_error_status_code():
    """잡 안에서 발생한 예외도 map_error()로 동기 경로와 동일하게 매핑돼야 한다(429 예시)."""
    app = create_app()
    app.state.interpreter = _FakeQueuedInterpreter(raise_exc=LLMRateLimitError("busy"))
    client = TestClient(app, raise_server_exceptions=False)
    job_id = client.post("/api/setlist", json={"prompt": "신나는 한 시간"}).json()["job_id"]
    r = _poll_until_terminal(client, job_id)
    assert r.status_code == 429
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "RATE_LIMITED"


def test_unknown_job_id_returns_404(client):
    r = client.get("/api/setlist/status/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_custom_mode_stays_synchronous_even_with_estimator(client):
    """커스텀 모드는 LLM을 안 쓰니 estimate_wait가 있어도 잡으로 안 빠지고 바로 200이어야 한다."""
    client.app.state.interpreter = _FakeQueuedInterpreter(wait_seconds=30.0)
    r = client.post("/api/setlist", json={
        "mode": "custom",
        "stages": [{"energy": 0.5, "minutes": 10}],
    })
    assert r.status_code == 200
    assert "job_id" not in r.json()


def test_estimated_wait_seconds_reflects_estimator(client):
    client.app.state.interpreter = _FakeQueuedInterpreter(wait_seconds=12.3)
    r = client.post("/api/setlist", json={"prompt": "신나는 한 시간"})
    assert r.status_code == 202
    assert r.json()["estimated_wait_seconds"] == 12.3


def test_response_includes_queue_position():
    """워커 1개짜리 큐에서 두 번째 요청은 앞에 1명(첫 요청) 있다고 나와야 한다."""
    from app.jobs import JobStore

    app = create_app()
    interp = _BlockingQueuedInterpreter()
    app.state.interpreter = interp
    app.state.job_store = JobStore(max_workers=1, max_queue_len=10)  # 순차 실행 강제(테스트 결정성용)
    client = TestClient(app, raise_server_exceptions=False)
    try:
        r1 = client.post("/api/setlist", json={"prompt": "첫 번째"})
        assert r1.json()["queue_position"] == 0  # 아무도 안 앞섰음
        r2 = client.post("/api/setlist", json={"prompt": "두 번째"})
        assert r2.json()["queue_position"] == 1  # r1이 아직 안 끝났으니 1명 대기
        status2 = client.get(f"/api/setlist/status/{r2.json()['job_id']}").json()
        assert status2["queue_position"] == 1
    finally:
        interp.release()


def test_queue_full_returns_429():
    """대기열 정원(REQUEST_QUEUE_MAX)을 넘기면 잡을 만들지 않고 즉시 429 QUEUE_FULL."""
    os.environ["REQUEST_QUEUE_MAX"] = "1"
    try:
        app = create_app()
        interp = _BlockingQueuedInterpreter()
        app.state.interpreter = interp
        client = TestClient(app, raise_server_exceptions=False)
        try:
            r1 = client.post("/api/setlist", json={"prompt": "첫 번째"})
            assert r1.status_code == 202  # 정원(1) 안에서는 통과
            r2 = client.post("/api/setlist", json={"prompt": "두 번째"})
            assert r2.status_code == 429
            assert r2.json()["error"]["code"] == "QUEUE_FULL"
        finally:
            interp.release()
    finally:
        del os.environ["REQUEST_QUEUE_MAX"]
