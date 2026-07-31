"""
Configuration for lyric_gate_ordering query generation.

Adapted from selection_pipeline/config_v2.py, with paths scoped to this folder.
"""
import os
from pathlib import Path

# ============================================================================
# Base paths
# ============================================================================
_SCRIPT_DIR = Path(__file__).parent
TOPIC_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = TOPIC_DIR.parent

# Output and work directories (scoped to this folder)
OUT_DIR = _SCRIPT_DIR / "out"
WORK_DIR = _SCRIPT_DIR / "work"

# ============================================================================
# LLM Configuration
# ============================================================================
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TEMPERATURE = 0.7  # Higher temperature for creative query generation


def get_groq_api_key():
    """Load GROQ_API_KEY from environment or work/groq.key file."""
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
# Band list (from data/songs_master.csv)
# ============================================================================
# Excluding metadata tags: ikka_dumb_rock, millsage, various_artists
VALID_BANDS = [
    "afterglow",
    "ave_mujica",
    "hello_happy_world",
    "morfonica",
    "mugendai_mutype",
    "mygo",
    "pastel_palettes",
    "poppin_party",
    "raise_a_suilen",
    "roselia",
]

# ============================================================================
# Query generation targets
# ============================================================================
CATEGORIES = {
    "band_specified": "밴드지정",
    "intensity_brightness": "강도밝기",
    "situational_functional": "상황기능",
    "progressive_arc": "진행형아크",
}

# Target counts per category
QUERIES_PER_CATEGORY = 150
BATCH_SIZE = 20  # Number of queries to generate in one LLM call
