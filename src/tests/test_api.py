"""API 계약·CORS·에러 테스트. 스텁 어댑터(오프라인)로 구동 — 네트워크 호출 없음."""

import os

os.environ["MOOD_INTERPRETER"] = "stub"  # create_app 임포트 전에 오프라인 강제

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_setlist_happy_path(client):
    r = client.post("/api/setlist", json={"prompt": "기분 좋아지는 신나는 1시간 플레이리스트"})
    assert r.status_code == 200
    body = r.json()
    assert body["picks"], "picks가 비어 있으면 안 됨"
    assert "params" in body and "stages" in body
    assert body["estimated_total_seconds"] > 0
    # 첫 곡은 seed
    assert body["picks"][0]["reason"]["harmonic"] == "seed"
    # 곡 중복 없음
    idxs = [p["idx"] for p in body["picks"]]
    assert len(idxs) == len(set(idxs))


def test_setlist_respects_request_overrides(client):
    r = client.post("/api/setlist", json={"prompt": "차분한 곡", "target_minutes": 30, "stage_count": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["stage_count"] == 2
    assert len(body["stages"]) == 2


def test_empty_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={"prompt": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_out_of_range_minutes_is_invalid_request(client):
    r = client.post("/api/setlist", json={"prompt": "x", "target_minutes": 999})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_cors_allows_configured_dev_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_does_not_wildcard(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    # 허용 목록 밖 오리진은 echo 되지 않아야 하며 와일드카드('*')도 아니어야 한다.
    assert r.headers.get("access-control-allow-origin") not in ("*", "http://evil.example.com")
