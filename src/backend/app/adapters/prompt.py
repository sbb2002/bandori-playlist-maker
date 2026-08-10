"""LLM 시스템 프롬프트 + 출력 JSON 파싱/검증 → MoodParameters.

어댑터가 LLM 원시 응답을 받아 검증·클램프·기본값 주입 후 도메인 모델로 변환하는 로직.
스키마1(architecture.md §③)의 검증 규칙을 단일 지점에 집약한다 — OpenRouter/스텁 공용.
"""

from __future__ import annotations

import json
import random

from ..domain.models import MoodParameters
from ..domain.tags import ensure_min_tags
from ..ports.mood_port import MoodInterpretationError

# 스키마1 기본값·범위(architecture.md §③ 스키마1 표).
_BRIGHTNESS_RANGE = (-1.0, 1.0)
_ENERGY_RANGE = (0.0, 1.0)
_STAGE_RANGE = (2, 5)
_MINUTES_RANGE = (10, 180)
_SUMMARY_MAX = 120
_MIN_STAGE_MINUTES = 3.0  # 프론트 app.js MIN_WIDTH_MIN과 동일 하한(구간이 너무 촘촘해지는 것 방지)

DEFAULT_BRIGHTNESS = 0.0
DEFAULT_START_ENERGY = 0.4
DEFAULT_STAGE_COUNT = 3
# 3단계: MoodParameters.stage_params 항목의 수치 키(StageSpec/Stage와 동일 이름, 전부 0.0~1.0).
_STAGE_PARAM_KEYS = (
    "valence", "lufs_integrated", "lra",
    "danceability_norm", "instr_stem_ratio", "speech_median",
)
# 프로토타입(epic/improved-playlist-maker, 다중 파라미터 체제 위 가사 감상 매칭): 6개 수치와
# 별도로 자유 텍스트 1개. 곡 쪽 가사 감상 임베딩(data/lyric_impressions.json)과 코사인 유사도로
# 비교해 Stage A 4순위 타이브레이크에 쓴다(selection.py._lyric_similarity).
_IMPRESSION_KEY = "impression"
_IMPRESSION_MAX_LEN = 100

# impression 예시 문장 풀 — 숫자 지터와 같은 문제의식(고정 예시 리터럴 복사 방지)을 텍스트에
# 적용: 콜마다 다른 문장을 순환시켜 모델이 예시를 그대로 베끼지 못하게 한다.
_IMPRESSION_EXAMPLE_POOL = [
    "안도와 위로 속에서도 옅은 그리움이 남는 잔잔한 정서",
    "설렘과 확신이 뒤섞인 채 앞으로 나아가려는 밝은 다짐",
    "지치고 무거운 마음을 다독이며 조용히 스스로를 추스르는 정서",
    "터질 듯한 흥분과 해방감으로 가득한 들뜬 정서",
    "쓸쓸함과 그리움이 배어나는 애틋하고 차분한 정서",
    "작은 희망을 붙잡고 앞으로 걸어가려는 담담한 의지",
]

# 3.5단계(2026-08-03) 함정 수정: 아래 stage_params/stage_minutes 예시에 고정 숫자를 쓰면
# 모델이 실제 분포를 계산하지 않고 예시 숫자를 그대로(또는 거의 그대로) 복사해버리는 현상이
# 실측에서 확인됨(예: "신나는 파티"류 요청마다 매번 예시와 소수점까지 동일한 값 반환).
# 그래서 예시 숫자를 요청마다 약간씩(±0.06) jitter해 새로 만든다 — 모델이 패턴을 그대로
# 베낄 수 없게 해, "그대로 베끼지 말라"는 지시문이 실제로 강제되도록 한다.
_BALLAD_EXAMPLE_TEMPLATE = {
    "valence": 0.3, "lufs_integrated": 0.25, "lra": 0.7,
    "danceability_norm": 0.2, "instr_stem_ratio": 0.45, "speech_median": 0.35,
}
_PARTY_EXAMPLE_TEMPLATE = {
    "valence": 0.85, "lufs_integrated": 0.8, "lra": 0.25,
    "danceability_norm": 0.85, "instr_stem_ratio": 0.55, "speech_median": 0.5,
}
_DRIVE_EXAMPLE_STAGE_TEMPLATES = [
    {"valence": 0.55, "lufs_integrated": 0.4, "lra": 0.55,
     "danceability_norm": 0.4, "instr_stem_ratio": 0.5, "speech_median": 0.45},
    {"valence": 0.7, "lufs_integrated": 0.65, "lra": 0.4,
     "danceability_norm": 0.65, "instr_stem_ratio": 0.5, "speech_median": 0.5},
    {"valence": 0.85, "lufs_integrated": 0.8, "lra": 0.3,
     "danceability_norm": 0.8, "instr_stem_ratio": 0.55, "speech_median": 0.55},
]


def _jitter_stage_params(template: dict[str, float], rng: random.Random, spread: float = 0.06) -> dict[str, float]:
    return {k: round(_clamp(v + rng.uniform(-spread, spread), 0.0, 1.0), 2) for k, v in template.items()}


def _build_dynamic_examples(rng: random.Random) -> str:
    """stage_params/stage_minutes 예시 문구를 요청마다 jitter된 새 숫자로 생성한다."""
    ballad2 = [_jitter_stage_params(_BALLAD_EXAMPLE_TEMPLATE, rng) for _ in range(2)]
    party1 = _jitter_stage_params(_PARTY_EXAMPLE_TEMPLATE, rng)
    drive_stages = [_jitter_stage_params(t, rng) for t in _DRIVE_EXAMPLE_STAGE_TEMPLATES]
    # impression도 숫자와 같은 이유로 매 콜마다 다른 예시 문장을 순환시켜 그대로 복사 방지.
    impression_pool = list(_IMPRESSION_EXAMPLE_POOL)
    rng.shuffle(impression_pool)
    for stage, text in zip(drive_stages, impression_pool):
        stage[_IMPRESSION_KEY] = text
    ballad_json = json.dumps(ballad2, ensure_ascii=False)
    party_json = json.dumps(party1, ensure_ascii=False)
    drive_stage_minutes = [20, 20, 20]
    full_example = {
        "brightness": 0.7, "start_energy": 0.35, "end_energy": 0.85, "stage_count": 3,
        "target_minutes": 60, "interpretation_summary": "주말을 여는 설레는 드라이브, 점점 달아오르는 한 시간",
        "tags": ["드라이브", "설렘", "주말", "고조되는"], "song_type": "all", "same_as_previous": False,
        "stage_minutes": drive_stage_minutes, "stage_params": drive_stages,
    }
    return (
        "  아래 예시의 숫자는 매 요청마다 무작위로 바뀌는 **자리표시자일 뿐이다 — 그대로 베끼거나 "
        "패턴만 흉내내지 말고** 반드시 [지표 분포 통계]의 실제 분포에서 값을 골라라(같은 카테고리 "
        "요청이라도 곡 풀·분포가 다르면 값도 달라져야 정상이다). "
        f"예: 조용한 발라드 2단계→{ballad_json}, "
        f"신나는 파티 1단계 예시 객체→{party_json}.\n\n"
        f"예: {json.dumps(full_example, ensure_ascii=False)}"
    )


SYSTEM_PROMPT = (
    "You are the mood interpreter for a BanG Dream! music setlist generator. Read the user's "
    "natural-language request and reply with ONLY the JSON schema below (no code block, no "
    "explanation). Never fall back lazily to defaults or null when the request is ambiguous — "
    "actively infer from context (e.g. a 5km run implies ~40 minutes).\n\n"
    "Fields:\n"
    "- brightness: -1.0 to 1.0. Positive for upbeat/bright requests, negative for calm/dark ones.\n"
    "- start_energy: 0.0 to 1.0. Low (0.1-0.25) for calm/quiet, high (0.6-0.8) for hype/exercise.\n"
    "- end_energy: 0.0 to 1.0. Only higher than start_energy if the request explicitly implies "
    "a build-up; otherwise keep it close to start_energy.\n"
    "- stage_count: integer 2-5. Match the number of energy shifts (2-3 for a simple rise/fall/flat, "
    "4-5 for activities with ups and downs). Do not default to 3 every time.\n"
    "- stage_energies: (optional) array of length 2-5. Fill for non-monotonic arcs like exercise "
    "(e.g. [0.3,0.7,0.85,0.5]). Overrides start_energy/end_energy/stage_count when given.\n"
    "- stage_minutes: array of length stage_count, summing to ~target_minutes, never null. If the "
    "user implies a specific section's length, reflect only that section differently; otherwise "
    "split evenly.\n"
    "- stage_bands: (optional) array of length stage_count, string|null. Fill only when the user "
    "explicitly splits time across named bands, using their exact wording; otherwise null — never "
    "invent a band.\n"
    "- target_minutes: integer 10-180. Use the stated value if given; otherwise estimate from the "
    "activity; null only if there is truly no clue.\n"
    "- interpretation_summary: one warm Korean sentence (<=80 chars) describing the mood, no numbers.\n"
    "- tags: 2-5 Korean keywords, no '#', never empty.\n"
    "- song_type: \"all\"|\"original\"|\"cover\" — only set original/cover if explicitly mentioned.\n"
    "- same_as_previous: boolean, meaningful only when a previous request is provided (true if same "
    "intent).\n"
    "- stage_params: array of length stage_count, never null. Each object has 6 floats (0.0-1.0) "
    "plus impression:\n"
    "  - valence (emotional brightness, same direction as brightness)\n"
    "  - lufs_integrated (perceived loudness, tracks energy)\n"
    "  - lra (dynamic range: higher for ballads, lower for party/EDM)\n"
    "  - danceability_norm (rhythmic drive, tracks energy)\n"
    "  - instr_stem_ratio (instrumental weight; use the median if unspecified)\n"
    "  - speech_median (lyric density: higher for rap, lower for ballads; median if unspecified)\n"
    "  If [지표 분포 통계] (feature distribution stats) is given, ground each value in that "
    "distribution (min~median or median~max) instead of defaulting to 0.5; prefer the matching "
    "band's row if one band is requested.\n"
    "  - impression: a Korean sentence (<=40 chars, in Korean) describing the *lyrical* mood of this "
    "stage — an emotional description, not a number. Never empty or null.\n"
)

# OpenRouter response_format용 JSON 스키마(structured output 지원 모델에서 사용).
RESPONSE_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "mood_parameters",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "brightness": {"type": "number"},
                "start_energy": {"type": "number"},
                "end_energy": {"type": "number"},
                "stage_count": {"type": "integer"},
                "stage_energies": {"type": ["array", "null"], "items": {"type": "number"}},
                "stage_minutes": {"type": ["array", "null"], "items": {"type": "number"}},
                "stage_bands": {"type": ["array", "null"], "items": {"type": ["string", "null"]}},
                "stage_params": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "valence": {"type": ["number", "null"]},
                            "lufs_integrated": {"type": ["number", "null"]},
                            "lra": {"type": ["number", "null"]},
                            "danceability_norm": {"type": ["number", "null"]},
                            "instr_stem_ratio": {"type": ["number", "null"]},
                            "speech_median": {"type": ["number", "null"]},
                            "impression": {"type": ["string", "null"]},
                        },
                        "required": [
                            "valence", "lufs_integrated", "lra",
                            "danceability_norm", "instr_stem_ratio", "speech_median",
                            "impression",
                        ],
                    },
                },
                "target_minutes": {"type": ["integer", "null"]},
                "interpretation_summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5},
                "song_type": {"type": "string", "enum": ["all", "original", "cover"]},
                "same_as_previous": {"type": "boolean"},
            },
            "required": [
                "brightness",
                "start_energy",
                "end_energy",
                "stage_count",
                "stage_energies",
                "stage_minutes",
                "stage_bands",
                "stage_params",
                "target_minutes",
                "interpretation_summary",
                "tags",
                "song_type",
                "same_as_previous",
            ],
        },
    },
}


def _format_feature_stats(feature_stats: dict) -> str:
    """feature_stats({"전체"|밴드명: {지표: {min,max,mean,median,std}}})를 프롬프트 블록으로.

    한 그룹당 한 줄, 지표당 min/max/mean/median/std 5개 값(소수 2자리) — LLM이 stage_params를
    실제 분포에 근거해 고르게 하는 재료(시스템 프롬프트의 [지표 분포 통계] 참조 지시와 짝).
    """
    lines = [
        "[지표 분포 통계] 후보 곡 풀의 오디오 지표 분포(stage_params와 동일한 전체 minmax "
        "스케일 0~1). 형식: 지표=min/max/mean/median/std."
    ]
    for group, metrics in feature_stats.items():
        parts = [
            f"{name}={s['min']:.2f}/{s['max']:.2f}/{s['mean']:.2f}/{s['median']:.2f}/{s['std']:.2f}"
            for name, s in metrics.items()
        ]
        lines.append(f"{group}: " + " · ".join(parts))
    return "\n".join(lines)


def build_messages(
    user_prompt: str, previous_prompt: str | None = None,
    feature_stats: dict | None = None,
) -> list[dict]:
    """OpenRouter/Groq chat/completions messages 배열을 만든다.

    previous_prompt가 주어지면(2회차+ 요청) 직전 요청과 현재 요청을 함께 제시하고, 두 요청이
    '본질적으로 같은 의도'인지 same_as_previous로 판정하게 한다(핫픽스: 세부설정 우선순위 결정).
    파라미터는 항상 '현재 요청' 기준으로 산출한다.
    feature_stats가 주어지면 시스템 메시지 끝에 [지표 분포 통계] 블록을 덧붙인다.
    """
    if previous_prompt and previous_prompt.strip():
        user_content = (
            "아래는 직전 회차 요청과 현재 회차 요청이다. 두 요청이 본질적으로 같은 의도인지 판단해 "
            "same_as_previous(true/false)로 표기하라. 나머지 파라미터는 반드시 '현재 요청' 기준으로 산출한다.\n"
            f"[직전 요청]\n{previous_prompt.strip()}\n\n[현재 요청]\n{user_prompt}"
        )
    else:
        user_content = user_prompt
    # 예시 숫자를 요청마다 새로 jitter(모델의 예시-그대로-복사 방지, 위 _build_dynamic_examples 참고).
    system_content = SYSTEM_PROMPT + "\n" + _build_dynamic_examples(random.Random())
    if feature_stats:
        system_content += "\n\n" + _format_feature_stats(feature_stats)
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _coerce_number(raw: object, default: float) -> float:
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _extract_json_object(text: str) -> dict:
    """LLM 원시 텍스트에서 첫 JSON 객체를 관용적으로 추출한다(코드펜스·군말 허용)."""
    text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise MoodInterpretationError(f"응답에서 JSON 객체를 찾지 못했습니다: {text[:200]!r}")
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise MoodInterpretationError(f"JSON 파싱 실패: {exc}") from exc
    if not isinstance(obj, dict):
        raise MoodInterpretationError(f"JSON 최상위가 객체가 아닙니다: {type(obj).__name__}")
    return obj


def parse_mood(raw_text: str) -> MoodParameters:
    """LLM 원시 응답 문자열을 검증·클램프·기본값 주입해 MoodParameters로 변환한다.

    누락 필드는 기본값을 주입하고, 범위 밖 값은 클램프한다. 완전 파싱 불가 시에만
    MoodInterpretationError(재시도 없음, PRD §7).
    """
    obj = _extract_json_object(raw_text)

    brightness = _clamp(_coerce_number(obj.get("brightness"), DEFAULT_BRIGHTNESS), *_BRIGHTNESS_RANGE)
    start_energy = _clamp(_coerce_number(obj.get("start_energy"), DEFAULT_START_ENERGY), *_ENERGY_RANGE)
    # end_energy 누락 시 start_energy로(진행 방향 = 차이).
    end_default = start_energy
    end_energy = _clamp(_coerce_number(obj.get("end_energy"), end_default), *_ENERGY_RANGE)

    try:
        stage_count = int(obj.get("stage_count", DEFAULT_STAGE_COUNT))
    except (TypeError, ValueError):
        stage_count = DEFAULT_STAGE_COUNT
    stage_count = int(_clamp(stage_count, *_STAGE_RANGE))

    target_minutes = obj.get("target_minutes")
    if target_minutes is not None:
        try:
            target_minutes = int(_clamp(int(target_minutes), *_MINUTES_RANGE))
        except (TypeError, ValueError):
            target_minutes = None

    summary = obj.get("interpretation_summary", "")
    if not isinstance(summary, str):
        summary = ""
    summary = summary.strip()[:_SUMMARY_MAX]

    # 비단조 아크(선택): 길이 2~5 실수 배열이면 클램프, 아니면 None(선형 아크로 폴백).
    stage_energies = obj.get("stage_energies")
    if isinstance(stage_energies, list) and 2 <= len(stage_energies) <= 5:
        try:
            stage_energies = [_clamp(float(e), *_ENERGY_RANGE) for e in stage_energies]
        except (TypeError, ValueError):
            stage_energies = None
    else:
        stage_energies = None

    # 3.5단계: 단계별 길이(분) 의도(선택). 길이가 stage_count와 다르면(모델이 배열 길이를
    # 못 맞춤) 신뢰하지 않고 None으로 폴백(선곡 엔진이 균등분배로 되돌아간다).
    stage_minutes = obj.get("stage_minutes")
    if isinstance(stage_minutes, list) and len(stage_minutes) == stage_count:
        try:
            stage_minutes = [max(_MIN_STAGE_MINUTES, float(m)) for m in stage_minutes]
        except (TypeError, ValueError):
            stage_minutes = None
    else:
        stage_minutes = None

    # 프로토타입: 단계별 밴드 고정(선택). 길이가 stage_count와 다르면(모델이 배열 길이를 못
    # 맞춤) 신뢰하지 않고 None으로 폴백. 실제로 프롬프트에서 언급된 밴드인지의 검증(라우트가
    # detect_bands()와 대조)은 여기서 하지 않는다 — 여기선 형태만 정리.
    stage_bands = obj.get("stage_bands")
    if isinstance(stage_bands, list) and len(stage_bands) == stage_count:
        stage_bands = [b.strip() if isinstance(b, str) and b.strip() else None for b in stage_bands]
    else:
        stage_bands = None

    # 3단계: 단계별 신규 오디오 파라미터(선택). 배열 길이가 stage_count와 다르면(모델이 단계
    # 수를 안 맞췄거나 통째로 이상하면) 신뢰할 수 없다고 보고 전체를 None으로 폴백한다.
    # 개별 항목 안에서는 필드 하나가 이상해도 그 필드만 None 처리하고 나머지는 살린다.
    stage_params = obj.get("stage_params")
    if isinstance(stage_params, list) and len(stage_params) == stage_count:
        parsed_stage_params: list[dict[str, float | None]] = []
        for entry in stage_params:
            if not isinstance(entry, dict):
                parsed_stage_params.append({})
                continue
            row: dict[str, float | str | None] = {}
            for key in _STAGE_PARAM_KEYS:
                v = entry.get(key)
                if v is None:
                    row[key] = None
                    continue
                try:
                    row[key] = _clamp(float(v), *_ENERGY_RANGE)
                except (TypeError, ValueError):
                    row[key] = None
            # impression은 수치 6개와 별도 분기(문자열, clamp 대상 아님) — 공백만이면 None.
            impression_raw = entry.get(_IMPRESSION_KEY)
            if isinstance(impression_raw, str) and impression_raw.strip():
                row[_IMPRESSION_KEY] = impression_raw.strip()[:_IMPRESSION_MAX_LEN]
            else:
                row[_IMPRESSION_KEY] = None
            parsed_stage_params.append(row)
        stage_params = parsed_stage_params
    else:
        stage_params = None

    # LLM이 태그를 누락/부족(0~1개)하게 줘도 요약 카드가 허전하지 않도록 최소 2개 보장.
    # 부족분은 산출된 무드 파라미터에서 대표 키워드를 결정론적으로 파생해 채운다.
    tags = ensure_min_tags(
        _clean_tags(obj.get("tags")),
        brightness,
        start_energy,
        end_energy,
        target_minutes,
    )

    song_type = str(obj.get("song_type", "all")).strip().lower()
    if song_type not in ("all", "original", "cover"):
        song_type = "all"

    # 직전 요청과 같은 의도인지 LLM 판정(직전 프롬프트가 제공된 경우만 의미). 불리언이 아니면 None
    # → 라우트가 previous_prompt 존재 여부와 함께 override 적용 여부를 안전하게 가른다.
    raw_same = obj.get("same_as_previous")
    same_as_previous = raw_same if isinstance(raw_same, bool) else None

    return MoodParameters(
        brightness=brightness,
        start_energy=start_energy,
        end_energy=end_energy,
        stage_count=stage_count,
        target_minutes=target_minutes,
        interpretation_summary=summary,
        stage_energies=stage_energies,
        tags=tags,
        song_type=song_type,
        same_as_previous=same_as_previous,
        stage_params=stage_params,
        stage_minutes=stage_minutes,
        stage_bands=stage_bands,
    )


def _clean_tags(raw: object) -> list[str] | None:
    """해시태그 키워드 정제 — 문자열만, 선행 # 제거, 중복 제거, 최대 5개, 길이 20 캡."""
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = item.strip().lstrip("#").strip()[:20]
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            out.append(tag)
        if len(out) >= 5:
            break
    return out or None
