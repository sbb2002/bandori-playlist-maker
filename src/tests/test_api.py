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


def test_ai_mode_never_honors_overrides(client):
    """AI 모드는 항상 honor=False라 사용자 override(재생시간·단계수)를 무시하고 모델이
    새로 제어한다(routes.py의 honor 판정 참고)."""
    r = client.post("/api/setlist", json={
        "prompt": "차분한 곡", "target_minutes": 30, "stage_count": 2,
    })
    assert r.status_code == 200
    body = r.json()
    # 스텁 기본 단계수는 3 — override(2)가 항상 무시됨을 확인.
    assert body["params"]["stage_count"] == 3
    assert len(body["stages"]) == 3


def test_first_request_ignores_user_overrides(client):
    """AI 모드는 사용자 override를 무시하고 모델이 전 파라미터를 제어한다."""
    r = client.post("/api/setlist", json={"prompt": "차분한 곡", "target_minutes": 30, "stage_count": 5})
    assert r.status_code == 200
    # 스텁 기본 단계수는 3 — override(5)가 무시됐음을 확인.
    assert r.json()["params"]["stage_count"] == 3


def test_response_exposes_honored_overrides(client):
    """honored_overrides는 AI 모드에서 항상 False다(커스텀 모드는 test_custom_mode_* 쪽에서
    항상 True인지 별도로 검증한다)."""
    r = client.post("/api/setlist", json={"prompt": "차분한 곡"})
    assert r.json()["honored_overrides"] is False


def test_empty_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={"prompt": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_prompt_is_invalid_request(client):
    r = client.post("/api/setlist", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_original_only_excludes_covers(client):
    # 커버/오리지널은 스코프 필터라 항상 명시값 적용.
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


def test_no_song_type_mention_is_original(client):
    # 체크박스 미지정 + 언급 없음 → song_type=original(기본값, 2026-08-24) → 오리지널만.
    r = client.post("/api/setlist", json={"prompt": "신나는 곡"})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["song_type"] == "original"
    assert body["include_original"] is True and body["include_cover"] is False
    assert all("(cover)" not in p["song"].lower() for p in body["picks"])


def test_all_keyword_sets_all(client):
    # 체크박스 미지정 + 프롬프트에 '모든/전곡' 등 명시적 전체 언급 → song_type=all → 둘 다 포함.
    r = client.post("/api/setlist", json={"prompt": "모든 곡 다 들려줘"})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["song_type"] == "all"
    assert body["include_original"] is True and body["include_cover"] is True


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Butter-Fly (Cover)", True),
        ("チョコレイトの低音レシピ (Solo)", True),
        ("唱 (feat. 仲町あられ・峰月律)", True),
        ("Redo", False),
        ("Feathered Dreams", False),  # "feat" 부분문자열이지만 '(feat.' 태그가 아님
    ],
)
def test_is_cover_detects_solo_and_feat_variants(title, expected):
    # Solo/feat.도 오리지널이 아닌 파생 버전이라 cover 필터에서만 등장해야 함(회귀 방지).
    from app.api.routes import _is_cover

    class _Song:
        song = title

    assert _is_cover(_Song()) is expected


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
    assert {"idx", "band", "song", "video_id", "camelot", "energy", "song_romaji", "song_hangul", "song_hanja_reading"} <= set(s0)
    # 로마자/한글/한자음은 pykakasi/hanja로 로드 시 계산되는 검색 보조 필드 — 빈 문자열이어도 됨(한자 없으면).
    assert all(s["song_romaji"] and s["song_hangul"] for s in songs)
    # 한자음은 한자가 없는 곡이면 원문 그대로(빈 문자열 아님)
    assert all("song_hanja_reading" in s for s in songs)
    # 밴드→곡 순 정렬
    keys = [(s["band"], s["song"].lower()) for s in songs]
    assert keys == sorted(keys)


def test_feature_stats_endpoint(client):
    r = client.get("/api/feature-stats")
    assert r.status_code == 200
    body = r.json()
    assert "total_eligible" in body and body["total_eligible"] > 0
    assert body["bins_1d"] == 12
    # 모든 1D 히스토그램이 12 bin을 가져야 함
    histograms = body["histograms"]
    for key in ["energy", "valence", "lufs_integrated", "lra", "danceability_norm", "instr_stem_ratio", "speech_median"]:
        assert key in histograms, f"histogram key '{key}' missing"
        bins = histograms[key]
        assert len(bins) == 12, f"histogram '{key}' has {len(bins)} bins, expected 12"
        # None을 스킵했으므로 합계는 total_eligible 이하여야 함 (정규값이 없으면 0일 수도)
        assert sum(bins) <= body["total_eligible"], f"histogram '{key}' sum > total_eligible"
    # 2D 조인 히스토그램 검증
    map_2d = body["map_2d"]
    assert map_2d["x_field"] == "valence"
    assert map_2d["y_field"] == "energy"
    assert map_2d["bins"] == 8
    grid = map_2d["grid"]
    assert len(grid) == 8, f"grid has {len(grid)} rows, expected 8"
    for row in grid:
        assert len(row) == 8, f"grid row has {len(row)} cols, expected 8"
        assert isinstance(row[0], int), "grid values should be ints"
    # 2D grid의 총합도 total_eligible 이하여야 함(valence가 None이면 제외)
    grid_sum = sum(sum(row) for row in grid)
    assert grid_sum <= body["total_eligible"]


def test_band_filter_restricts_to_selected(client):
    r = client.post("/api/setlist", json={"prompt": "신나는 곡", "bands": ["poppin_party"]})
    assert r.status_code == 200
    body = r.json()
    assert {p["band"] for p in body["picks"]} == {"poppin_party"}


def test_manual_band_filter_always_applies(client):
    """밴드는 스코프 필터라 항상 적용된다(honor와 무관)."""
    r = client.post("/api/setlist", json={
        "prompt": "조용한 수면 음악", "bands": ["poppin_party"],
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


# ── 스테이지별 고정 밴드 검증(프로토타입, LLM이 지어낸 값 무효화) ──────────────────

def test_validate_stage_bands_keeps_values_within_detected_set():
    from app.api.routes import _validate_stage_bands
    detected = {"morfonica", "mugendai_mutype"}
    raw = ["모르포니카", "개유노"]
    assert _validate_stage_bands(raw, detected) == ["morfonica", "mugendai_mutype"]


def test_validate_stage_bands_nulls_hallucinated_band():
    from app.api.routes import _validate_stage_bands
    detected = {"morfonica"}  # 프롬프트에 mygo는 언급 안 됨
    raw = ["모르포니카", "마이고"]
    assert _validate_stage_bands(raw, detected) == ["morfonica", None]


def test_validate_stage_bands_none_and_empty_list_passthrough():
    from app.api.routes import _validate_stage_bands
    assert _validate_stage_bands(None, {"morfonica"}) is None
    assert _validate_stage_bands([], {"morfonica"}) == []


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


def test_custom_mode_ignores_prompt_band_auto_detect(client):
    """커스텀 모드는 payload.bands만 스코프 필터로 쓴다 — prompt에 다른 밴드명이 있어도
    자동감지로 섞이지 않는다(설계의도, 2026-08-24 명시화: 이전엔 프론트가 커스텀 모드
    요청에 prompt를 안 보내서 우연히 이렇게 됐을 뿐, 백엔드는 모드 무관하게 감지했었다)."""
    r = client.post("/api/setlist", json={
        "prompt": "로젤리아랑 라스 노래로", "mode": "custom", "bands": ["morfonica"],
        "stages": [{"energy": 0.5, "song_count": 3}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["applied_bands"] == ["morfonica"]
    assert {p["band"] for p in body["picks"]} == {"morfonica"}


def test_custom_stages_override(client):
    # mode="custom"은 항상 사용자 stages를 그대로 존중한다.
    r = client.post("/api/setlist", json={
        "prompt": "아무거나", "mode": "custom",
        "stages": [{"energy": 0.2, "minutes": 5}, {"energy": 0.85, "minutes": 5}],
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["stages"]) == 2
    assert [s["energy_target"] for s in body["stages"]] == [0.2, 0.85]
    assert body["params"]["stage_count"] == 2


def test_custom_stage_song_count(client):
    r = client.post("/api/setlist", json={
        "prompt": "아무거나", "mode": "custom",
        "stages": [{"energy": 0.3, "song_count": 2}, {"energy": 0.7, "song_count": 4}],
    })
    assert r.status_code == 200
    picks = r.json()["picks"]
    assert sum(1 for p in picks if p["stage_index"] == 0) == 2
    assert sum(1 for p in picks if p["stage_index"] == 1) == 4


def test_many_stages_up_to_eleven(client):
    """핫픽스 제안2: 수동 그래프는 최대 11구간까지 허용(기존 5 상한 확장)."""
    stages = [{"energy": round(0.2 + 0.05 * i, 2), "song_count": 1} for i in range(11)]
    r = client.post("/api/setlist", json={"prompt": "아무거나", "mode": "custom", "stages": stages})
    assert r.status_code == 200
    assert len(r.json()["stages"]) == 11


def test_twelve_stages_is_invalid(client):
    """12구간(분리선 11개)은 스키마 검증에서 거부(최대 11구간)."""
    stages = [{"energy": 0.5, "song_count": 1} for _ in range(12)]
    r = client.post("/api/setlist", json={"prompt": "x", "stages": stages})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_stage_without_size_is_invalid(client):
    r = client.post("/api/setlist", json={"prompt": "x", "stages": [{"energy": 0.5}]})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


# ── 검색 보조 필드 테스트(로마자·한글·한자음) ──────────────────────────────────────
def test_songs_search_includes_hanja_reading_field(client):
    """곡 목록 응답에 한자음 검색 필드가 포함된다."""
    r = client.get("/api/songs")
    assert r.status_code == 200
    songs = r.json()["songs"]
    assert songs
    # 모든 곡이 song_hanja_reading 필드를 가져야 함(한자 없으면 원문)
    for s in songs:
        assert "song_hanja_reading" in s
        assert isinstance(s["song_hanja_reading"], str)


def test_refresh_data_forbidden_when_token_not_configured(client, monkeypatch):
    monkeypatch.delenv("DATA_REFRESH_TOKEN", raising=False)
    r = client.post("/api/admin/refresh-data")
    assert r.status_code == 403


def test_refresh_data_forbidden_with_wrong_token(client, monkeypatch):
    monkeypatch.setenv("DATA_REFRESH_TOKEN", "correct-token")
    r = client.post("/api/admin/refresh-data", headers={"X-Refresh-Token": "wrong-token"})
    assert r.status_code == 403


def test_refresh_data_succeeds_with_correct_token(client, monkeypatch):
    monkeypatch.setenv("DATA_REFRESH_TOKEN", "correct-token")
    calls = []

    def fake_refresh(*, force):
        calls.append(force)
        return client.app.state.songs  # 기존 곡 목록 그대로 반환(단위테스트라 네트워크 안 탐)

    monkeypatch.setattr(client.app.state, "refresh_songs", fake_refresh)
    r = client.post("/api/admin/refresh-data", headers={"X-Refresh-Token": "correct-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["song_count"] == len(client.app.state.songs)
    assert calls == [True]


# ── AI 모드 / 커스텀 모드 토글 테스트 ──────────────────────────────────────────────
def test_custom_mode_requires_stages(client):
    """커스텀 모드는 stages가 필수."""
    r = client.post("/api/setlist", json={"mode": "custom"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_custom_mode_builds_from_stages(client):
    """커스텀 모드는 stages를 받아 직접 세트리스트 구성."""
    r = client.post("/api/setlist", json={
        "mode": "custom",
        "stages": [{"energy": 0.2, "minutes": 5}, {"energy": 0.85, "minutes": 5}],
        "target_minutes": 10,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["interpretation_summary"] == ""
    assert body["params"]["stage_count"] == 2
    assert len(body["stages"]) == 2
    assert body["stages"][0]["energy_target"] == 0.2
    assert body["stages"][1]["energy_target"] == 0.85


def test_custom_mode_new_stage_fields_echoed(client):
    """커스텀 모드에서 신규 필드(valence 등)가 요청에 있으면 응답에도 있어야 한다."""
    r = client.post("/api/setlist", json={
        "mode": "custom",
        "stages": [
            {
                "energy": 0.5,
                "song_count": 2,
                "valence": 0.7,
                "lufs_integrated": -10.5,
                "lra": 8.2,
                "danceability_norm": 0.6,
                "instr_stem_ratio": 0.8,
                "speech_median": 0.1,
            }
        ],
    })
    assert r.status_code == 200
    body = r.json()
    stage0 = body["stages"][0]
    assert stage0["valence"] == 0.7
    assert stage0["lufs_integrated"] == -10.5
    assert stage0["lra"] == 8.2
    assert stage0["danceability_norm"] == 0.6
    assert stage0["instr_stem_ratio"] == 0.8
    assert stage0["speech_median"] == 0.1


def test_custom_mode_skips_llm_interpreter(client, monkeypatch):
    """커스텀 모드에서는 LLM interpreter.interpret이 호출되지 않아야 한다."""
    calls = []

    def fake_interpret(prompt, energy_stats=None, feature_stats=None, lang="ko", acquired_event=None):
        calls.append(prompt)
        raise RuntimeError("interpreter.interpret should not be called in custom mode")

    monkeypatch.setattr(client.app.state, "interpreter", type("FakeInterpreter", (), {"interpret": fake_interpret})())
    r = client.post("/api/setlist", json={
        "mode": "custom",
        "stages": [{"energy": 0.5, "song_count": 1}],
    })
    assert r.status_code == 200
    assert calls == []  # interpreter.interpret 호출 안 됨


def test_ai_mode_stage_params_flow_to_response(client, monkeypatch):
    """3단계: AI 모드 첫 요청도(honor 무관) LLM이 채운 stage_params가 응답 stages에 실려야 한다."""
    from app.domain.models import MoodParameters

    def fake_interpret(self, prompt, energy_stats=None, feature_stats=None, lang="ko", acquired_event=None):
        return MoodParameters(
            brightness=0.5, start_energy=0.4, end_energy=0.4, stage_count=2,
            target_minutes=20, interpretation_summary="test",
            stage_params=[
                {"valence": 0.8, "lufs_integrated": 0.6},
                {"valence": 0.3, "instr_stem_ratio": 0.9},
            ],
        )

    monkeypatch.setattr(client.app.state, "interpreter", type("FakeInterpreter", (), {"interpret": fake_interpret})())
    r = client.post("/api/setlist", json={"prompt": "아무거나"})
    assert r.status_code == 200
    stages = r.json()["stages"]
    assert len(stages) == 2
    assert stages[0]["valence"] == 0.8
    assert stages[0]["lufs_integrated"] == 0.6
    assert stages[1]["valence"] == 0.3
    assert stages[1]["instr_stem_ratio"] == 0.9


def test_ai_mode_default_when_mode_omitted(client):
    """mode 필드를 생략하면 기본값 'ai'로 동작(회귀 테스트)."""
    r = client.post("/api/setlist", json={"prompt": "신나는 곡"})
    assert r.status_code == 200
    body = r.json()
    assert "params" in body and "stages" in body


def test_empty_prompt_still_invalid_in_ai_mode(client):
    """AI 모드(기본)에서는 빈 prompt가 여전히 무효."""
    r = client.post("/api/setlist", json={"prompt": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_prompt_still_invalid_in_ai_mode(client):
    """AI 모드(명시적)에서 prompt 없음은 무효."""
    r = client.post("/api/setlist", json={"mode": "ai"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_custom_mode_with_null_new_fields(client):
    """커스텀 모드에서 신규 필드가 null이면 응답에도 null."""
    r = client.post("/api/setlist", json={
        "mode": "custom",
        "stages": [{"energy": 0.5, "song_count": 1, "valence": None}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["stages"][0]["valence"] is None
