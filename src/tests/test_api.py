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


# ── 설정 기능(§5-1) ───────────────────────────────────────────────────────────
def test_bands_endpoint(client):
    r = client.get("/api/bands")
    assert r.status_code == 200
    bands = r.json()["bands"]
    assert bands, "밴드 목록이 비어 있으면 안 됨"
    assert all("band" in b and "count" in b for b in bands)
    # count 내림차순 정렬
    counts = [b["count"] for b in bands]
    assert counts == sorted(counts, reverse=True)


def test_band_filter_restricts_to_selected(client):
    r = client.post("/api/setlist", json={"prompt": "신나는 곡", "bands": ["poppin_party"]})
    assert r.status_code == 200
    body = r.json()
    assert {p["band"] for p in body["picks"]} == {"poppin_party"}


def test_prompt_band_name_auto_filters(client):
    r = client.post("/api/setlist", json={"prompt": "라스 노래로 신나게 틀어줘"})
    assert r.status_code == 200
    assert {p["band"] for p in r.json()["picks"]} == {"raise_a_suilen"}


def test_empty_bands_is_all(client):
    r = client.post("/api/setlist", json={"prompt": "신나는 곡", "bands": []})
    assert r.status_code == 200
    assert len({p["band"] for p in r.json()["picks"]}) >= 1


def test_custom_stages_override(client):
    r = client.post("/api/setlist", json={
        "prompt": "아무거나",
        "stages": [{"energy": 0.2, "minutes": 5}, {"energy": 0.85, "minutes": 5}],
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["stages"]) == 2
    assert [s["energy_target"] for s in body["stages"]] == [0.2, 0.85]
    assert body["params"]["stage_count"] == 2


def test_custom_stage_song_count(client):
    r = client.post("/api/setlist", json={
        "prompt": "아무거나",
        "stages": [{"energy": 0.3, "song_count": 2}, {"energy": 0.7, "song_count": 4}],
    })
    assert r.status_code == 200
    picks = r.json()["picks"]
    assert sum(1 for p in picks if p["stage_index"] == 0) == 2
    assert sum(1 for p in picks if p["stage_index"] == 1) == 4


def test_stage_without_size_is_invalid(client):
    r = client.post("/api/setlist", json={"prompt": "x", "stages": [{"energy": 0.5}]})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
