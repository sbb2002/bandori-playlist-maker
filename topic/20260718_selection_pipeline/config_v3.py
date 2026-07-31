"""Configuration for selection_pipeline v3 (Method 1 vs Method 2, real production reuse).

DESIGN_v3.md: Method 1 = prod_snapshot.domain.selection.build_setlist() as-is.
Method 2 = prod_snapshot.domain.selection_stage_c.build_setlist_with_stage_c().
"""
import math
import os
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
TOPIC_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = TOPIC_DIR.parent

PROD_SNAPSHOT_DIR = _SCRIPT_DIR / "prod_snapshot"
IDX_DESC_CSV = _SCRIPT_DIR / "out" / "v3_idx_desc.csv"

OUT_DIR = _SCRIPT_DIR / "out" / "v3"
WORK_DIR = _SCRIPT_DIR / "work"

# DESIGN_v3.md §3: production adapter default model (not the .env deployed override).
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TEMPERATURE = 0.2  # matches GroqMoodInterpreter.interpret()
EMBED_MODEL = "BAAI/bge-m3"

K = 3  # DESIGN_v3.md §4: fixed song_count per single forced stage
SEED_BASE = 20260721  # DESIGN_v3.md §4: rng seed per query = SEED_BASE + query_index
SHUFFLE_SEED = 20260721  # blind sheet shuffle seed


def get_groq_api_key():
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        return api_key
    key_file = WORK_DIR / "groq.key"
    if key_file.exists():
        return key_file.read_text().strip()
    raise ValueError("GROQ_API_KEY not found. Set env GROQ_API_KEY or create work/groq.key")


def compute_candidate_pool_size(pool_size: int) -> int:
    """Must match prod_snapshot/domain/selection_stage_c.py's Stage C formula exactly."""
    return max(15, math.ceil(0.20 * pool_size))


# DESIGN_v3.md §5.1 — 24 queries, R01~R24.
QUERIES: dict[str, dict] = {
    "R01": {"text": "poppin'party 노래로 신나게 하루 시작하고 싶어.", "category": "band"},
    "R02": {"text": "roselia 노래 중에 무겁고 진지한 분위기로 틀어줘.", "category": "band"},
    "R03": {"text": "raise a suilen 노래로 미친듯이 달리고 싶어.", "category": "band"},
    "R04": {"text": "mygo 노래로 조용히 감성에 잠기고 싶어.", "category": "band"},
    "R05": {"text": "ave mujica 노래로 스산하고 어두운 분위기 잡고 싶어.", "category": "band"},
    "R06": {"text": "hello happy world 노래로 밝고 유쾌하게 놀고 싶어.", "category": "band"},
    "R07": {"text": "완전 조용하고 힘 빠진 노래로 채워줘.", "category": "intensity_brightness"},
    "R08": {"text": "미친듯이 텐션 폭발하는 노래로 채워줘.", "category": "intensity_brightness"},
    "R09": {"text": "햇살 가득한 것처럼 밝은 노래 듣고 싶어.", "category": "intensity_brightness"},
    "R10": {"text": "칠흑같이 어둡고 무거운 노래 듣고 싶어.", "category": "intensity_brightness"},
    "R11": {"text": "중간 정도 텐션에 살짝 우울한 느낌으로.", "category": "intensity_brightness"},
    "R12": {"text": "살짝 들뜨는데 시끄럽진 않은 노래로.", "category": "intensity_brightness"},
    "R13": {"text": "헬스장에서 웨이트 할 때 들을 노래.", "category": "situational"},
    "R14": {"text": "독서할 때 배경으로 틀어놓을 노래.", "category": "situational"},
    "R15": {"text": "장거리 운전할 때 졸음 안 오게 들을 노래.", "category": "situational"},
    "R16": {"text": "빨래 개면서 듣기 좋은 노래.", "category": "situational"},
    "R17": {"text": "친구 생일파티에서 틀 노래.", "category": "situational"},
    "R18": {"text": "잠들기 전 조명 끄고 듣는 노래.", "category": "situational"},
    "R19": {"text": "달리기 준비운동부터 본운동, 마무리까지 이어지는 러닝 플레이리스트.", "category": "arc"},
    "R20": {"text": "천천히 달아오르는 파티 분위기로 만들어줘.", "category": "arc"},
    "R21": {"text": "가라앉은 기분에서 서서히 힘을 되찾는 느낌으로.", "category": "arc"},
    "R22": {"text": "공부 시작할 때 차분하다가 집중력 오르면서 점점 몰입되는 느낌으로.", "category": "arc"},
    "R23": {"text": "새벽 드라이브, 조용히 출발해서 해뜰 때쯤 신나지는 느낌으로.", "category": "arc"},
    "R24": {"text": "운동 마무리하고 차분히 식히는 쿨다운 느낌으로.", "category": "arc"},
}
