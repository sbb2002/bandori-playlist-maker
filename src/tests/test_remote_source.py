"""remote_source 재시도·degraded 폴백(stale 캐시/번들 fallback) 회귀 테스트.

실제 네트워크는 절대 타지 않는다 — httpx.MockTransport로 fetch 성공/실패를 흉내낸다.
"""

from __future__ import annotations

import httpx
import pytest

from app.repo.remote_source import _ensure_data_file


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _always_fail(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="boom")


def test_succeeds_on_first_try(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, content=b"fresh,data\n1,a\n")

    cache_path = tmp_path / "songs_master.csv"
    path, degraded, reason = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path, env_override=None,
        force=False, repo="r", branch="b", timeout=5.0, client=_client(handler),
        required=True, attempts=3, backoff_seconds=0,
    )
    assert path == cache_path
    assert degraded is False
    assert reason is None
    assert len(calls) == 1
    assert cache_path.read_bytes() == b"fresh,data\n1,a\n"


def test_retries_then_succeeds(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, content=b"ok\n")

    cache_path = tmp_path / "songs_master.csv"
    path, degraded, reason = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path, env_override=None,
        force=False, repo="r", branch="b", timeout=5.0, client=_client(handler),
        required=True, attempts=3, backoff_seconds=0,
    )
    assert degraded is False
    assert len(calls) == 3
    assert cache_path.read_bytes() == b"ok\n"


def test_falls_back_to_stale_cache_after_retries_exhausted(tmp_path):
    cache_path = tmp_path / "songs_master.csv"
    cache_path.write_bytes(b"stale,cache\n")

    path, degraded, reason = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path, env_override=None,
        force=True,  # force=True라 캐시가 있어도 재요청을 시도함
        repo="r", branch="b", timeout=5.0, client=_client(_always_fail),
        required=True, attempts=3, backoff_seconds=0,
    )
    assert path == cache_path
    assert degraded is True
    assert reason is not None and "3회 재시도" in reason
    assert cache_path.read_bytes() == b"stale,cache\n"  # 캐시가 fetch 실패로 덮어써지지 않았어야 함


def test_falls_back_to_bundled_snapshot_when_no_cache(tmp_path):
    fallback = tmp_path / "fallback.csv"
    fallback.write_bytes(b"bundled,snapshot\n")
    cache_path = tmp_path / "cache" / "songs_master.csv"

    path, degraded, reason = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path, env_override=None,
        force=False, repo="r", branch="b", timeout=5.0, client=_client(_always_fail),
        required=True, fallback_path=fallback, attempts=3, backoff_seconds=0,
    )
    assert path == cache_path
    assert degraded is True
    assert cache_path.read_bytes() == b"bundled,snapshot\n"


def test_raises_when_required_and_no_cache_no_fallback(tmp_path):
    cache_path = tmp_path / "songs_master.csv"

    with pytest.raises(RuntimeError, match="3회 재시도"):
        _ensure_data_file(
            filename="songs_master.csv", cache_path=cache_path, env_override=None,
            force=False, repo="r", branch="b", timeout=5.0, client=_client(_always_fail),
            required=True, attempts=3, backoff_seconds=0,
        )


def test_returns_none_when_not_required_and_no_cache_no_fallback(tmp_path):
    cache_path = tmp_path / "lyric_impressions.json"

    path, degraded, reason = _ensure_data_file(
        filename="lyric_impressions.json", cache_path=cache_path, env_override=None,
        force=False, repo="r", branch="b", timeout=5.0, client=_client(_always_fail),
        required=False, attempts=3, backoff_seconds=0,
    )
    assert path is None
    assert degraded is True
    assert reason is not None
