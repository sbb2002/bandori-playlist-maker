import os
from pathlib import Path

# Base paths (relative to this script's directory)
_SCRIPT_DIR = Path(__file__).parent

# ============================================================================
# §5 Base Constants (DESIGN.md)
# ============================================================================
SEED = 42
TOP_K = 5
SONGS_CSV = _SCRIPT_DIR / "../../../mfcc_analysis/selected_songs.csv"

# §7 Override: Local sample run — 14 songs from 7 bands × 2 songs
SAMPLE_TAGS = [
    "afterglow__000", "afterglow__001", "ave_mujica__072", "ave_mujica__073",
    "hello_happy_world__106", "hello_happy_world__107", "morfonica__180", "morfonica__181",
    "mugendai_mutype__237", "mugendai_mutype__238", "mygo__260", "mygo__261",
    "pastel_palettes__301", "pastel_palettes__302",
]
AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"

# §7 Override: Local stems in work/ instead of mfcc_analysis/stems/htdemucs
STEMS_DIR = _SCRIPT_DIR / "work/stems"

# ASR
# §7 Override: medium instead of large-v3 for time budget
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium")
WHISPER_COMPUTE = "int8"  # CPU-based
# faster-whisper parameters (no change needed):
#   language=None, vad_filter=True, temperature=0.0,
#   condition_on_previous_text=False, beam_size=5

# Embedding
EMBED_MODEL = "BAAI/bge-m3"
# Fallback: intfloat/multilingual-e5-small

# LLM (Groq)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE = 0.0

# §7 Override: GROQ_API_KEY from env or work/groq.key file
def get_groq_api_key():
    """Load GROQ_API_KEY from environment or work/groq.key file."""
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        return api_key
    key_file = _SCRIPT_DIR / "work/groq.key"
    if key_file.exists():
        return key_file.read_text().strip()
    raise ValueError(
        "GROQ_API_KEY not found. Set env GROQ_API_KEY or create work/groq.key"
    )

GROQ_API_KEY = None  # Will be loaded on demand in scripts

# Evaluation queries: 4 categories × 2 levels (L1, L4) = 8 queries
# (From DESIGN.md §5 — do not modify wording)
CATEGORIES = {
    "C1": "슬픔/우울",
    "C2": "가련함/나아감",
    "C3": "힙함/세련됨/시티팝",
    "C4": "밝음/아침/위로",
}

PROMPTS = {
    "C1-L1": "우울하고 슬픈 노래 틀어줘.",
    "C1-L4": "짙은 밤하늘 아래 홀로 남겨진 듯한 고독감이 밀려오지만, 애써 담담하게 슬픔을 받아들이며 조용히 내면을 위로하는 애절하고 서정적인 정서.",
    "C2-L1": "희망찬데 슬픈 노래.",
    "C2-L4": "금방이라도 부서질 것처럼 연약하고 서글픈 보컬의 목소리 뒤로, 세차게 몰아치는 드럼과 기타 사운드가 질주하며 불안 속에서도 끝내 딛고 일어나 나아가고자 하는 아련하고 가련한 의지.",
    "C3-L1": "힙하고 세련된 노래.",
    "C3-L4": "지나치게 무겁지 않은 미디엄 템포 위에 재지(Jazzy)한 건반과 찰진 베이스 리듬이 얹혀, 도회적인 고독과 낭만이 교차하는 감각적이고 스타일리시한 무드.",
    "C4-L1": "아침에 듣기 좋은 밝은 노래.",
    "C4-L4": "이른 아침의 맑은 공기와 부드러운 햇살이 스며들 듯, 어쿠스틱한 악기들이 만드는 포근한 공간감 속에서 불안을 걷어내고 긍정적인 온기를 불어넣는 나른하면서도 화사한 순간.",
}

# Output directory
OUT_DIR = _SCRIPT_DIR / "out"

# Work directory
WORK_DIR = _SCRIPT_DIR / "work"
