"""
Configuration for energy_selection experiment.

DESIGN.md §1, §4: Paths, Groq model, trials, queries, and parameters.
"""
import os
from pathlib import Path

# ============================================================================
# Base paths
# ============================================================================
_SCRIPT_DIR = Path(__file__).parent
OUT_DIR = _SCRIPT_DIR / "out"
WORK_DIR = _SCRIPT_DIR / "work"

# ============================================================================
# LLM Model (DESIGN.md §1, §4)
# ============================================================================
# Groq default model from deployment (groq_adapter.py DEFAULT_MODEL)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# Groq temperature — deployment adapter (groq_adapter.py) uses 0.2, confirmed via
# `git show main:src/backend/app/adapters/groq_adapter.py`.
GROQ_TEMPERATURE = 0.2

# ============================================================================
# Experiment Parameters (DESIGN.md §4)
# ============================================================================
N_TRIALS = 5  # number of independent calls per query-variant pair
SEED = 20260718

# Variants to test (DESIGN.md §5, §9)
VARIANTS = ["baseline", "candidate_A", "candidate_B", "candidate_AB", "candidate_E"]


def get_groq_api_key():
    """Load GROQ_API_KEY from environment or work/groq.key file.

    Pattern from selection_pipeline/config.py.
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
