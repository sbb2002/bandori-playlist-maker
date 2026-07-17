import os
from pathlib import Path

# Base paths (relative to this script's directory)
_SCRIPT_DIR = Path(__file__).parent

# ============================================================================
# §1 Base Constants (DESIGN.md)
# ============================================================================

# Seeds and parameters
SEED = 20260717  # DESIGN.md §5
ALPHA = 0.5       # DESIGN.md §4c — α=0.5 for main evaluation
ALPHA_SENSITIVITY = [0.25, 0.75]  # DESIGN.md §4c — for sensitivity analysis only

# Songs catalog
SONGS_CSV = _SCRIPT_DIR / "full_catalog_songs.csv"

# Acoustic features (from songs_master.csv)
SONGS_MASTER_CSV = _SCRIPT_DIR.parent.parent.parent.parent / "data" / "songs_master.csv"

# Ground truth labels for audit
GROUND_TRUTH_LABELS_CSV = _SCRIPT_DIR.parent.parent.parent.parent / "data" / "ground_truth_labels.csv"

# Method-1 reference data
METHOD_1_DIR = _SCRIPT_DIR.parent / "method-1"
METHOD_1_OUT_DIR = METHOD_1_DIR / "out"

# Embedding
EMBED_MODEL = "BAAI/bge-m3"

# LLM (Groq)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_TEMPERATURE = 0.0

# §7 Override: GROQ_API_KEY from env or work/groq.key file
def get_groq_api_key():
    """Load GROQ_API_KEY from environment or work/groq.key file."""
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        return api_key
    key_file = _SCRIPT_DIR / "work" / "groq.key"
    if key_file.exists():
        return key_file.read_text().strip()
    # Fallback to method-1's key file
    key_file_m1 = METHOD_1_DIR / "work" / "groq.key"
    if key_file_m1.exists():
        return key_file_m1.read_text().strip()
    raise ValueError(
        "GROQ_API_KEY not found. Set env GROQ_API_KEY or create work/groq.key"
    )

# Stage 2 queries (from method-1/config.py, copied exactly as-is per DESIGN.md §3)
STAGE2_QUERIES = {
    "T1-Q1": {"tier": "T1_literal", "text": "행복한 노래 틀어줘."},
    "T1-Q2": {"tier": "T1_literal", "text": "슬픈 노래 틀어줘."},
    "T2-Q1": {"tier": "T2_idiomatic", "text": "요즘 좀 꿀꿀해. 그런 기분에 어울리는 노래 틀어줘."},
    "T2-Q2": {"tier": "T2_idiomatic", "text": "날아갈 것처럼 신나는 기분이야. 그런 노래 틀어줘."},
    "T3-Q1": {"tier": "T3_metaphorical", "text": "먼저 떠난 이가 불러주는 듯한 위로의 노래를 듣고 싶어."},
    "T3-Q2": {"tier": "T3_metaphorical", "text": "부드럽고 포근한 자장가 같은 노래를 듣고 싶어."},
}

# Output directory
OUT_DIR = _SCRIPT_DIR / "out"

# Work directory
WORK_DIR = _SCRIPT_DIR / "work"
