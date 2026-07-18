"""
Configuration for selection_pipeline experiment v2 (arm1 vs arm2, 84 queries).

DESIGN_v2.md: Replication with 84 queries (§1: 82 needed for 80% power, +2 margin).
Arm3 excluded. Seed changed to avoid overlap with v1 blind sheet shuffle.
"""
import os
from pathlib import Path

# ============================================================================
# Base paths
# ============================================================================
_SCRIPT_DIR = Path(__file__).parent
TOPIC_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = TOPIC_DIR.parent

# Paths to dependencies (method-1 and method-2)
METHOD1_DIR = TOPIC_DIR / "vector-embedding" / "src" / "method-1"
METHOD2_DIR = TOPIC_DIR / "vector-embedding" / "src" / "method-2"

# Input files (DESIGN.md §1)
FULL_CATALOG_CSV = METHOD1_DIR / "full_catalog_songs.csv"
SONG_ACOUSTICS_CSV = METHOD2_DIR / "out" / "song_acoustics.csv"
SONG_PROFILES_CSV = METHOD1_DIR / "out" / "song_profiles.csv"

# Output directory — v2 results isolated in out/v2
OUT_DIR = _SCRIPT_DIR / "out" / "v2"

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
# Pipeline Parameters (DESIGN_v2.md §4)
# ============================================================================
K = 1  # top-K results per arm per query (v2: reduced from v1's K=3 — DESIGN_v2.md §7.
       # Primary judgment (§0) is the query-level paired Wilcoxon over 84 query pairs;
       # that pair count alone already meets the n=82 power target regardless of K, so
       # extra items per query beyond the single closest match aren't needed for the
       # pre-registered test and only add listening burden. Changed before any scoring
       # started, so pre-registration integrity is unaffected.)
TOL = 0.08  # tolerance window for intensity matching
SEED = 20260720  # v2 reshuffle #2 — bumped after the drawer accidentally exposed
                 # category grouping to the evaluator before scoring began; picking a
                 # fresh seed avoids any chance the previously-seen order primes scoring.

# ============================================================================
# Queries (DESIGN_v2.md §2 — 84 queries, Q101~Q184)
# ============================================================================
# §2a: Band-specified + relative emotion (Q101~Q121, 21 queries)
# §2b: Band-agnostic + absolute intensity (Q122~Q142, 21 queries)
# §2c: Situational/functional (Q143~Q163, 21 queries)
# §2d: Brightness recheck (Q164~Q184, 21 queries)
QUERIES = {
    # ========================================================================
    # 2a. 밴드지정+상대감성 (Q101~Q121)
    # ========================================================================
    "Q101": {
        "text": "poppin'party 노래 중에 제일 잔잔한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q102": {
        "text": "poppin'party 노래 중에서 제일 신나는 곡 골라줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q103": {
        "text": "roselia 노래 중에 그나마 차분한 곡 있어?",
        "category": "band_specified_relative_emotion",
    },
    "Q104": {
        "text": "roselia 노래 중에 가장 격렬한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q105": {
        "text": "raise a suilen 노래 중에 상대적으로 힘 뺀 곡 알려줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q106": {
        "text": "raise a suilen에서 제일 폭주하는 느낌의 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q107": {
        "text": "pastel*palettes 노래 중에 비교적 잔잔한 곡 뭐 있어?",
        "category": "band_specified_relative_emotion",
    },
    "Q108": {
        "text": "pastel*palettes 노래 중에 제일 통통 튀는 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q109": {
        "text": "afterglow 노래 중에 가장 차분한 곡 골라줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q110": {
        "text": "afterglow 노래 중에 제일 열정적인 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q111": {
        "text": "hello happy world 노래 중에 상대적으로 잔잔한 곡 있어?",
        "category": "band_specified_relative_emotion",
    },
    "Q112": {
        "text": "hello happy world 노래 중에서 제일 신나는 곡으로 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q113": {
        "text": "morfonica 노래 중에 제일 차분한 곡 알려줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q114": {
        "text": "morfonica 노래 중에 가장 격정적인 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q115": {
        "text": "mygo 노래 중에서 제일 텐션 높은 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q116": {
        "text": "mygo 노래 중에 제일 잔잔한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q117": {
        "text": "ave mujica 노래 중에 비교적 잔잔한 곡 있어?",
        "category": "band_specified_relative_emotion",
    },
    "Q118": {
        "text": "ave mujica 노래 중에서 가장 강렬한 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q119": {
        "text": "무겐다이 뮤타입 노래 중에 그나마 차분한 곡 알려줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q120": {
        "text": "무겐다이 뮤타입 노래 중에서 제일 하이텐션인 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    "Q121": {
        "text": "roselia 노래 중에서 제일 웅장하고 폭발적인 곡 틀어줘.",
        "category": "band_specified_relative_emotion",
    },
    # ========================================================================
    # 2b. 밴드미지정+절대강도 (Q122~Q142)
    # ========================================================================
    "Q122": {
        "text": "장르 상관없이 진짜 조용하고 힘 뺀 노래 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q123": {
        "text": "빵빵 터지는 하이텐션 파티 노래로만 채워줘.",
        "category": "absolute_intensity",
    },
    "Q124": {
        "text": "완전 잔잔하고 소리 작은 노래만 골라줘.",
        "category": "absolute_intensity",
    },
    "Q125": {
        "text": "미친듯이 신나고 텐션 폭발하는 곡으로 부탁해.",
        "category": "absolute_intensity",
    },
    "Q126": {
        "text": "숨소리도 들릴 만큼 조용한 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q127": {
        "text": "귀청 떨어질 정도로 강렬한 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q128": {
        "text": "잔잔하다 못해 거의 무음에 가까운 곡 있어?",
        "category": "absolute_intensity",
    },
    "Q129": {
        "text": "심장 뛸 정도로 격렬한 곡으로 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q130": {
        "text": "밴드 상관없이 제일 다운된 느낌의 곡 알려줘.",
        "category": "absolute_intensity",
    },
    "Q131": {
        "text": "밴드 상관없이 제일 업된 느낌의 곡 알려줘.",
        "category": "absolute_intensity",
    },
    "Q132": {
        "text": "볼륨을 낮춰도 될 만큼 조용한 곡 부탁해.",
        "category": "absolute_intensity",
    },
    "Q133": {
        "text": "볼륨 최대로 키우고 싶은 강렬한 곡 부탁해.",
        "category": "absolute_intensity",
    },
    "Q134": {
        "text": "정말 힘 하나도 없는 저텐션 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q135": {
        "text": "에너지 폭발하는 고텐션 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q136": {
        "text": "그 어떤 곡보다 조용한 곡을 찾아줘.",
        "category": "absolute_intensity",
    },
    "Q137": {
        "text": "그 어떤 곡보다 시끄럽고 강한 곡을 찾아줘.",
        "category": "absolute_intensity",
    },
    "Q138": {
        "text": "잔잔한 걸로 아주 극단적인 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q139": {
        "text": "격렬한 걸로 아주 극단적인 곡 틀어줘.",
        "category": "absolute_intensity",
    },
    "Q140": {
        "text": "밴드 안 가리고 가장 차분한 곡 하나만 추천해줘.",
        "category": "absolute_intensity",
    },
    "Q141": {
        "text": "밴드 안 가리고 가장 폭발적인 곡 하나만 추천해줘.",
        "category": "absolute_intensity",
    },
    "Q142": {
        "text": "소리 세기가 제일 약한 곡으로 틀어줘.",
        "category": "absolute_intensity",
    },
    # ========================================================================
    # 2c. 상황/기능성 (Q143~Q163)
    # ========================================================================
    "Q143": {
        "text": "운동할 때 들으면 힘 나는 노래.",
        "category": "situational_functionality",
    },
    "Q144": {
        "text": "공부할 때 집중 잘 되는 노래.",
        "category": "situational_functionality",
    },
    "Q145": {
        "text": "드라이브할 때 듣기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q146": {
        "text": "새벽에 혼자 있을 때 듣고 싶은 노래.",
        "category": "situational_functionality",
    },
    "Q147": {
        "text": "출근길에 듣기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q148": {
        "text": "잠들기 전에 듣기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q149": {
        "text": "카페에서 공부하면서 틀어놓기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q150": {
        "text": "친구들이랑 파티할 때 틀 노래.",
        "category": "situational_functionality",
    },
    "Q151": {
        "text": "여행 갈 때 차 안에서 듣고 싶은 노래.",
        "category": "situational_functionality",
    },
    "Q152": {
        "text": "힘들 때 위로받고 싶은 노래.",
        "category": "situational_functionality",
    },
    "Q153": {
        "text": "일할 때 집중하기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q154": {
        "text": "지친 하루 끝에 힐링되는 노래.",
        "category": "situational_functionality",
    },
    "Q155": {
        "text": "집안일 하면서 틀어놓기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q156": {
        "text": "산책할 때 듣기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q157": {
        "text": "야근할 때 버티게 해주는 노래.",
        "category": "situational_functionality",
    },
    "Q158": {
        "text": "시험 공부할 때 듣는 노래.",
        "category": "situational_functionality",
    },
    "Q159": {
        "text": "이별하고 나서 듣고 싶은 노래.",
        "category": "situational_functionality",
    },
    "Q160": {
        "text": "기념일 분위기에 어울리는 노래.",
        "category": "situational_functionality",
    },
    "Q161": {
        "text": "캠핑 가서 듣기 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q162": {
        "text": "회식 자리에서 틀면 좋은 노래.",
        "category": "situational_functionality",
    },
    "Q163": {
        "text": "반신욕하면서 듣고 싶은 노래.",
        "category": "situational_functionality",
    },
    # ========================================================================
    # 2d. 밝기재확인 (Q164~Q184)
    # ========================================================================
    "Q164": {
        "text": "듣고 나면 기분이 조금 나아지는 노래.",
        "category": "brightness_recheck",
    },
    "Q165": {
        "text": "마음이 무겁고 가라앉는 밤에 어울리는 노래.",
        "category": "brightness_recheck",
    },
    "Q166": {
        "text": "웃음이 절로 나는 노래.",
        "category": "brightness_recheck",
    },
    "Q167": {
        "text": "눈물이 날 것 같은 노래.",
        "category": "brightness_recheck",
    },
    "Q168": {
        "text": "기분 전환하고 싶을 때 듣는 노래.",
        "category": "brightness_recheck",
    },
    "Q169": {
        "text": "우울할 때 더 우울해지고 싶은 노래.",
        "category": "brightness_recheck",
    },
    "Q170": {
        "text": "행복한 기분이 드는 노래.",
        "category": "brightness_recheck",
    },
    "Q171": {
        "text": "쓸쓸한 기분이 드는 노래.",
        "category": "brightness_recheck",
    },
    "Q172": {
        "text": "희망이 느껴지는 노래.",
        "category": "brightness_recheck",
    },
    "Q173": {
        "text": "슬픔에 잠기게 되는 노래.",
        "category": "brightness_recheck",
    },
    "Q174": {
        "text": "밝은 에너지가 느껴지는 노래.",
        "category": "brightness_recheck",
    },
    "Q175": {
        "text": "어두운 감성의 노래.",
        "category": "brightness_recheck",
    },
    "Q176": {
        "text": "긍정적인 기운을 주는 노래.",
        "category": "brightness_recheck",
    },
    "Q177": {
        "text": "센치해지는 노래.",
        "category": "brightness_recheck",
    },
    "Q178": {
        "text": "발랄한 기분이 드는 노래.",
        "category": "brightness_recheck",
    },
    "Q179": {
        "text": "울적한 기분이 드는 노래.",
        "category": "brightness_recheck",
    },
    "Q180": {
        "text": "미소가 지어지는 노래.",
        "category": "brightness_recheck",
    },
    "Q181": {
        "text": "눈물 참기 힘든 노래.",
        "category": "brightness_recheck",
    },
    "Q182": {
        "text": "기운이 나는 노래.",
        "category": "brightness_recheck",
    },
    "Q183": {
        "text": "가슴이 먹먹해지는 노래.",
        "category": "brightness_recheck",
    },
    "Q184": {
        "text": "설레는 기분이 드는 노래.",
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
# Candidate pool size (DESIGN.md §3, DESIGN_v2.md §0)
# ============================================================================
def compute_candidate_pool_size(eligible_pool_size):
    """
    N = max(15, ceil(0.20 * len(eligible_pool)))

    Ensures minimum 15 songs even if pool is small (e.g., ave_mujica 29 -> 15).
    """
    import math
    return max(15, math.ceil(0.20 * eligible_pool_size))
