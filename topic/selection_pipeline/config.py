"""
Configuration for selection_pipeline experiment.

DESIGN.md §5: config.py defines paths, LLM model, queries, and parameters.
"""
import os
from pathlib import Path

# ============================================================================
# Base paths
# ============================================================================
_SCRIPT_DIR = Path(__file__).parent
# selection_pipeline lives at topic/selection_pipeline, a sibling of
# topic/vector_embedding. TOPIC_DIR (== .../topic) is one level up, not two —
# a previous version used _SCRIPT_DIR.parent.parent (the repo root) and then
# appended "vector_embedding" directly, which skipped the "topic/" segment
# and pointed at a nonexistent path (repo_root/vector_embedding/... instead
# of repo_root/topic/vector_embedding/...), causing FileNotFoundError on
# every input CSV read.
TOPIC_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = TOPIC_DIR.parent

# Paths to dependencies (method-1 and method-2)
METHOD1_DIR = TOPIC_DIR / "vector_embedding" / "src" / "method-1"
METHOD2_DIR = TOPIC_DIR / "vector_embedding" / "src" / "method-2"

# Input files (DESIGN.md §1)
FULL_CATALOG_CSV = METHOD1_DIR / "full_catalog_songs.csv"
SONG_ACOUSTICS_CSV = METHOD2_DIR / "out" / "song_acoustics.csv"
SONG_PROFILES_CSV = METHOD1_DIR / "out" / "song_profiles.csv"

# Output directory
OUT_DIR = _SCRIPT_DIR / "out"

# Work directory
WORK_DIR = _SCRIPT_DIR / "work"

# ============================================================================
# LLM & Embedding Model (DESIGN.md §1, §5)
# ============================================================================
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_TEMPERATURE = 0.0
EMBED_MODEL = "BAAI/bge-m3"


def get_groq_api_key():
    """Load GROQ_API_KEY from environment or work/groq.key file.

    Pattern from method-1/config.py §7 override.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        return api_key
    key_file = WORK_DIR / "groq.key"
    if key_file.exists():
        return key_file.read_text().strip()
    raise ValueError(
        "GROQ_API_KEY not found. Set env GROQ_API_KEY or create work/groq.key"
    )


GROQ_API_KEY = None  # Will be loaded on demand in scripts

# ============================================================================
# Pipeline Parameters (DESIGN.md §5)
# ============================================================================
K = 3  # top-K results per arm per query
TOL = 0.08  # tolerance window for intensity matching
SEED = 20260717  # random seed for shuffling (§4c)

# ============================================================================
# Queries (DESIGN.md §2 — 신규 8개, T1~T3 재사용 금지)
# ============================================================================
# Format: query_id -> {"text": <natural language query>}
QUERIES = {
    "Q1": {
        "text": "mygo 노래 중에 제일 잔잔한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q2": {
        "text": "raise a suilen 노래 중에 그나마 차분한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q3": {
        "text": "장르 상관없이 진짜 조용하고 힘 뺀 노래 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q4": {
        "text": "빵빵 터지는 하이텐션 파티 노래로만 채워줘.",
        "category": "absolute_intensity",
    },
    "Q5": {
        "text": "운동할 때 들으면 힘 나는 노래.",
        "category": "situational_functionality",
    },
    "Q6": {
        "text": "새벽에 혼자 있을 때 듣고 싶은 노래.",
        "category": "situational_functionality",
    },
    "Q7": {
        "text": "듣고 나면 기분이 조금 나아지는 노래.",
        "category": "brightness_recheck",
    },
    "Q8": {
        "text": "마음이 무겁고 가라앉는 밤에 어울리는 노래.",
        "category": "brightness_recheck",
    },
}

# ============================================================================
# Band tags (from full_catalog_songs.csv, for LLM band extraction prompt)
# ============================================================================
# These must match exactly with full_catalog_songs.csv's "band" column values
# (excluding 'ikka_dumb_rock', 'millsage', 'various_artists' which are metadata tags)
VALID_BANDS = [
    "afterglow",
    "ave_mujica",
    "hello_happy_world",
    "mugendai_mutype",
    "mygo",
    "morfonica",
    "pastel_palettes",
    "poppin_party",
    "raise_a_suilen",
    "roselia",
]

# ============================================================================
# Candidate pool size (DESIGN.md §3)
# ============================================================================
def compute_candidate_pool_size(eligible_pool_size):
    """
    N = max(15, ceil(0.20 * len(eligible_pool)))

    Ensures minimum 15 songs even if pool is small (e.g., ave_mujica 29 -> 15).
    """
    import math
    return max(15, math.ceil(0.20 * eligible_pool_size))
