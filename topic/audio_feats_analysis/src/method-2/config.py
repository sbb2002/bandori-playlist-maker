"""Shared config for method-2: unified BPM candidate selection + bestdori validation."""
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # topic/audio_feats_analysis/src/method-2 -> repo root
TOPIC_OUT = PROJECT_ROOT / "topic" / "audio_feats_analysis" / "out"

AUDIO_FEATS_CSV = TOPIC_OUT / "audio_feats.csv"
BPM_SELECTED_CSV = TOPIC_OUT / "bpm_selected.csv"
BESTDORI_BPM_CSV = TOPIC_OUT / "bestdori_bpm.csv"
BPM_VALIDATION_CSV = TOPIC_OUT / "bpm_validation.csv"
BPM_FINAL_CSV = TOPIC_OUT / "bpm_final.csv"
BESTDORI_CACHE_DIR = TOPIC_OUT / "bestdori_cache"

# 후보군 범위 — 사용자가 bestdori를 skimming해 관측한 전곡 실제 BPM 근사 범위.
# report/01 §6.2에 따라 이번 파이프라인에서는 [85,220] 고정.
BPM_LO, BPM_HI = 85.0, 220.0
OCTAVES = [-1, 0, 1]  # ±2옥타브는 661곡 전체에서 범위에 든 사례 0건 (report/01 §6 검증)
TAU = 0.96  # 형제 프로젝트 perceptual_pulse() 튜닝값 — 대칭 적용

BESTDORI_ALL_URL = "https://bestdori.com/api/songs/all.5.json"
BESTDORI_SONG_URL = "https://bestdori.com/api/songs/{id}.json"
FETCH_SLEEP_SEC = 0.3

# 카탈로그 band -> bestdori bandId (게임 수록 밴드만; 나머지는 비교 모집단 제외)
BAND_ID = {
    "poppin_party": 1,
    "afterglow": 2,
    "hello_happy_world": 3,
    "pastel_palettes": 4,
    "roselia": 5,
    "raise_a_suilen": 18,
    "morfonica": 21,
    "mygo": 45,
    "ave_mujica": 46,
}

# MIREX 계열 템포 평가 표준 허용 오차(±4%) — Accuracy1(옥타브 불허)/Accuracy2(옥타브 허용) 판정에 사용
TEMPO_TOL = 0.04
