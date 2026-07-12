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
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body  # 프론트 우하단 버전 표기용
    assert body["interpreter"] == "stub"  # 활성 해석기 진단(테스트는 stub 강제) — 라이브 스텁 폴백 확인용


def test_setlist_response_is_not_cached(client):
    # 요약 카드 '고착' 방지: 세트리스트 응답은 브라우저/프록시 캐시 금지.
    r = client.post("/api/setlist", json={"prompt": "아무거나"})
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


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


def test_same_intent_honors_request_overrides(client):
    # 직전 요청과 의도가 같으면(previous_prompt 동봉) 사용자 override(재생시간·단계수)를 존중한다.
    r = client.post("/api/setlist", json={
        "prompt": "차분한 곡", "previous_prompt": "차분한 곡",
        "target_minutes": 30, "stage_count": 2,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["stage_count"] == 2
    assert len(body["stages"]) == 2


def test_first_request_ignores_user_overrides(client):
    """1회차(previous_prompt 없음)에는 사용자 override를 무시하고 모델이 전 파라미터를 제어한다."""
    r = client.post("/api/setlist", json={"prompt": "차분한 곡", "target_minutes": 30, "stage_count": 5})
    assert r.status_code == 200
    # 스텁 기본 단계수는 3 — override(5)가 무시됐음을 확인.
    assert r.json()["params"]["stage_count"] == 3


def test_changed_prompt_drops_stale_overrides(client):
    """직전과 의도가 '다른' 프롬프트면 사용자 override를 무시(프롬프트 바꾸면 자동 복귀)."""
    r = client.post("/api/setlist", json={
        "prompt": "신나는 파티 음악", "previous_prompt": "조용한 수면 음악",
        "stage_count": 2,
        "stages": [{"energy": 0.9, "minutes": 5}, {"energy": 0.9, "minutes": 5}],
    })
    assert r.status_code == 200
    # 의도가 달라 stages/stage_count override 무시 → 스텁 기본 단계수(3).
    assert r.json()["params"]["stage_count"] == 3


def test_response_exposes_honored_overrides(client):
    """응답의 honored_overrides로 프론트가 자동 해석(false) 시 그래프/재생시간을 되돌릴 수 있어야 한다."""
    r1 = client.post("/api/setlist", json={"prompt": "차분한 곡"})
    assert r1.json()["honored_overrides"] is False  # 1회차 → 자동
    r2 = client.post("/api/setlist", json={"prompt": "차분한 곡", "previous_prompt": "차분한 곡"})
    assert r2.json()["honored_overrides"] is True   # 같은 의도 → 재생 형태 override 존중
    r3 = client.post("/api/setlist", json={"prompt": "신나는 파티", "previous_prompt": "조용한 수면 명상"})
    assert r3.json()["honored_overrides"] is False  # 의도 변경 → 자동


def test_empty_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={"prompt": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_original_only_excludes_covers(client):
    # 커버/오리지널은 스코프 필터라 previous_prompt 없이(1회차)도 항상 명시값 적용.
    r = client.post("/api/setlist", json={"prompt": "아무거나", "include_original": True, "include_cover": False})
    assert r.status_code == 200
    assert all("(cover)" not in p["song"].lower() for p in r.json()["picks"])


def test_cover_only_includes_only_covers(client):
    r = client.post("/api/setlist", json={"prompt": "아무거나", "include_original": False, "include_cover": True})
    assert r.status_code == 200
    picks = r.json()["picks"]
    assert picks and all("(cover)" in p["song"].lower() for p in picks)


def test_cover_keyword_sets_cover_only(client):
    # 체크박스 미지정 + 프롬프트에 '커버' → LLM(stub) song_type=cover → 커버만 + 응답에 반영.
    r = client.post("/api/setlist", json={"prompt": "커버곡으로만 신나게"})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["song_type"] == "cover"
    assert body["include_original"] is False and body["include_cover"] is True
    assert all("(cover)" in p["song"].lower() for p in body["picks"])


def test_no_song_type_mention_is_all(client):
    # 체크박스 미지정 + 언급 없음 → song_type=all → 둘 다 포함(기본 ALL).
    r = client.post("/api/setlist", json={"prompt": "신나는 곡"})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["song_type"] == "all"
    assert body["include_original"] is True and body["include_cover"] is True


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


def test_songs_endpoint(client):
    r = client.get("/api/songs")
    assert r.status_code == 200
    songs = r.json()["songs"]
    assert songs, "곡 목록이 비어 있으면 안 됨"
    s0 = songs[0]
    assert {"idx", "band", "song", "video_id", "camelot", "energy"} <= set(s0)
    # 밴드→곡 순 정렬
    keys = [(s["band"], s["song"].lower()) for s in songs]
    assert keys == sorted(keys)


def test_band_filter_restricts_to_selected(client):
    r = client.post("/api/setlist", json={"prompt": "신나는 곡", "bands": ["poppin_party"]})
    assert r.status_code == 200
    body = r.json()
    assert {p["band"] for p in body["picks"]} == {"poppin_party"}


def test_manual_band_filter_always_applies_even_on_intent_change(client):
    """밴드는 스코프 필터라 의도가 바뀐 2회차에도 항상 적용된다(honor와 무관)."""
    r = client.post("/api/setlist", json={
        "prompt": "조용한 수면 음악", "previous_prompt": "신나는 파티 음악",
        "bands": ["poppin_party"],
    })
    assert r.status_code == 200
    assert r.json()["applied_bands"] == ["poppin_party"]
    assert {p["band"] for p in r.json()["picks"]} == {"poppin_party"}


def test_prompt_band_name_auto_filters(client):
    r = client.post("/api/setlist", json={"prompt": "라스 노래로 신나게 틀어줘"})
    assert r.status_code == 200
    body = r.json()
    assert {p["band"] for p in body["picks"]} == {"raise_a_suilen"}
    assert body["applied_bands"] == ["raise_a_suilen"]  # 프론트 체크박스 동기화용


def test_empty_bands_is_all(client):
    r = client.post("/api/setlist", json={"prompt": "신나는 곡", "bands": []})
    assert r.status_code == 200
    assert len({p["band"] for p in r.json()["picks"]}) >= 1


def test_prompt_bands_do_not_carry_across_requests(client):
    """요청 간 밴드 누적 방지(긴급버그): 프론트가 자동감지분을 재전송하지 않는 계약을 백엔드에서 고정.

    1차 프롬프트가 여러 밴드를 자동감지해도, 2차 요청(bands=[] + 다른 밴드 프롬프트)에는
    1차 밴드가 섞이지 않아야 한다 — 백엔드는 무상태로 이번 프롬프트 감지분만 적용.
    """
    r1 = client.post("/api/setlist", json={"prompt": "로젤리아랑 라스 노래로"})
    assert r1.status_code == 200
    assert set(r1.json()["applied_bands"]) == {"roselia", "raise_a_suilen"}

    r2 = client.post("/api/setlist", json={"prompt": "몰포 노래로", "bands": []})
    assert r2.status_code == 200
    assert r2.json()["applied_bands"] == ["morfonica"]
    assert {p["band"] for p in r2.json()["picks"]} == {"morfonica"}


def test_custom_stages_override(client):
    # 그래프 수동 단계(stages)도 의도가 같을 때만 적용 → previous_prompt 동봉.
    r = client.post("/api/setlist", json={
        "prompt": "아무거나", "previous_prompt": "아무거나",
        "stages": [{"energy": 0.2, "minutes": 5}, {"energy": 0.85, "minutes": 5}],
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["stages"]) == 2
    assert [s["energy_target"] for s in body["stages"]] == [0.2, 0.85]
    assert body["params"]["stage_count"] == 2


def test_custom_stage_song_count(client):
    r = client.post("/api/setlist", json={
        "prompt": "아무거나", "previous_prompt": "아무거나",
        "stages": [{"energy": 0.3, "song_count": 2}, {"energy": 0.7, "song_count": 4}],
    })
    assert r.status_code == 200
    picks = r.json()["picks"]
    assert sum(1 for p in picks if p["stage_index"] == 0) == 2
    assert sum(1 for p in picks if p["stage_index"] == 1) == 4


def test_many_stages_up_to_eleven(client):
    """핫픽스 제안2: 수동 그래프는 최대 11구간까지 허용(기존 5 상한 확장)."""
    stages = [{"energy": round(0.2 + 0.05 * i, 2), "song_count": 1} for i in range(11)]
    r = client.post("/api/setlist", json={"prompt": "아무거나", "previous_prompt": "아무거나", "stages": stages})
    assert r.status_code == 200
    assert len(r.json()["stages"]) == 11


def test_twelve_stages_is_invalid(client):
    """12구간(분리선 11개)은 스키마 검증에서 거부(최대 11구간)."""
    stages = [{"energy": 0.5, "song_count": 1} for _ in range(12)]
    r = client.post("/api/setlist", json={"prompt": "x", "previous_prompt": "x", "stages": stages})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_stage_without_size_is_invalid(client):
    r = client.post("/api/setlist", json={"prompt": "x", "stages": [{"energy": 0.5}]})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
