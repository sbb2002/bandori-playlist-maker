"""비동기 setlist 작업 큐 — TPM 페이싱 대기를 HTTP 요청 밖으로 빼내 폴링 가능하게 한다.

2026-08-10 이전엔 POST /api/setlist가 큐 대기(TokenBucketLimiter.acquire())를 요청 안에서
그대로 블로킹했다 — 대기가 길어지면(여러 요청이 몰려 TPM 예산을 다 쓴 경우) Render 같은
플랫폼의 리버스프록시 요청 타임아웃에 걸려 사용자에게 그냥 429/타임아웃으로 보였다.
이제 POST는 잡을 등록만 하고 즉시 202(job_id + 예상 대기초 + 대기 순번)로 응답, 실제 작업
(LLM 호출 포함)은 이 모듈의 스레드풀에서 돌며 GET /api/setlist/status/{job_id}로 진행상황을
폴링한다. 대기열 자체가 너무 길면(max_queue_len) 잡을 만들지 않고 즉시 429로 거절한다 —
스레드풀 내부 큐가 무한정 쌓이는 걸 막는 백프레셔.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .api.errors import QueueFullError, map_error

logger = logging.getLogger("setlist_maker")

_JOB_TTL_SECONDS = 300  # 완료 후 이 시간 지나면 정리(메모리 무한증가 방지) — 폴링 주기(수초) 대비 충분히 김


@dataclass
class Job:
    id: str
    seq: int  # 제출 순서(단조증가) — queue_position 계산용
    status: str = "queued"  # queued | running | done | error
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    result: dict | None = None
    error: dict | None = None  # {"status_code", "code", "message"}
    _estimate: Callable[[], float] | None = field(default=None, repr=False)
    # 폴링 응답에 실제로 내보낸 값 중 최솟값 — 아래 estimated_wait_seconds()가 단조감소를
    # 보장하는 데 쓴다(2026-08-12 버그 리포트: "0초까지 내려갔다가 다시 42초로 튐" 참고).
    _min_estimate: float | None = field(default=None, repr=False)

    def estimated_wait_seconds(self) -> float:
        """지금 시점 기준 예상 대기초(폴링마다 새로 계산 — 참고용, 위 rate_limiter 주석 참고).

        _estimate()는 TokenBucketLimiter.estimate_wait()를 그대로 호출하는 비소비성 조회라
        "지금 cost만큼의 토큰이 새로 필요하다면 얼마나 기다려야 하는가"만 안다 — 이 잡 자신의
        acquire()가 이미 성공해서 토큰을 소비한 뒤(=레이트리밋 대기는 끝났고 실제 LLM 응답을
        기다리는 단계)에도 계속 호출되므로, 방금 자신이 써버린 토큰 때문에 마치 다시 대기해야
        하는 것처럼 재계산돼버린다(레이트리밋 대기와 무관한 LLM 응답 지연을 레이트리밋 대기로
        오인). 그 결과 사용자에게는 "0초"까지 내려갔던 안내가 뜬금없이 다시 몇十초로 튀어
        보이는 버그가 됐다 — 한 번 관측된 최솟값 밑으로는 다시 올리지 않게 클램프해서 막는다.
        """
        if self.status in ("done", "error") or self._estimate is None:
            return 0.0
        try:
            wait = self._estimate()
        except Exception:  # noqa: BLE001 — 안내용 추정치 계산 실패는 무시(0으로 폴백)
            wait = 0.0
        wait = 0.0 if wait == float("inf") else round(wait, 1)
        if self._min_estimate is None or wait < self._min_estimate:
            self._min_estimate = wait
        return self._min_estimate


class JobStore:
    """인메모리 잡 저장소 + 실행용 스레드풀. 단일 프로세스 전제(Render free tier 1 인스턴스)."""

    def __init__(self, max_workers: int = 200, max_queue_len: int = 200) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._seq_counter = 0
        self._max_queue_len = max(1, max_queue_len)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="setlist-job")

    def submit(self, run: Callable[[], dict], estimate: Callable[[], float] | None = None) -> Job:
        with self._lock:
            self._gc_locked()
            pending = self._pending_count_locked()
            if pending >= self._max_queue_len:
                raise QueueFullError(f"대기열 정원({self._max_queue_len}) 초과(현재 {pending}건 대기 중).")
            self._seq_counter += 1
            job = Job(id=uuid.uuid4().hex, seq=self._seq_counter, _estimate=estimate)
            self._jobs[job.id] = job
        self._executor.submit(self._run_job, job, run)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._gc_locked()
            return self._jobs.get(job_id)

    def queue_position(self, job: Job) -> int:
        """이 잡보다 먼저 들어왔고 아직 안 끝난 잡 수(= 내 앞에 몇 명 있는지). 완료 시 0."""
        if job.status in ("done", "error"):
            return 0
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if j.seq < job.seq and j.status in ("queued", "running")
            )

    def _pending_count_locked(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

    @staticmethod
    def _run_job(job: Job, run: Callable[[], dict]) -> None:
        job.status = "running"
        try:
            job.result = run()
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 — 백그라운드 잡 예외는 FastAPI 핸들러가 못 잡으므로 여기서 직접 매핑
            status_code, code, message = map_error(exc)
            job.error = {"status_code": status_code, "code": code, "message": message}
            job.status = "error"
            if status_code == 500:
                logger.exception("백그라운드 setlist 잡 처리 중 오류: %s", exc)
        finally:
            job.finished_at = time.monotonic()

    def _gc_locked(self) -> None:
        now = time.monotonic()
        expired = [
            jid for jid, j in self._jobs.items()
            if j.finished_at is not None and now - j.finished_at > _JOB_TTL_SECONDS
        ]
        for jid in expired:
            del self._jobs[jid]
