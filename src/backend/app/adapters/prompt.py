"""LLM 시스템 프롬프트 + 출력 JSON 파싱/검증 → MoodParameters.

어댑터가 LLM 원시 응답을 받아 검증·클램프·기본값 주입 후 도메인 모델로 변환하는 로직.
스키마1(architecture.md §③)의 검증 규칙을 단일 지점에 집약한다 — OpenRouter/스텁 공용.
"""

from __future__ import annotations

import json

from ..domain.models import MoodParameters
from ..ports.mood_port import MoodInterpretationError

# 스키마1 기본값·범위(architecture.md §③ 스키마1 표).
_BRIGHTNESS_RANGE = (-1.0, 1.0)
_ENERGY_RANGE = (0.0, 1.0)
_STAGE_RANGE = (2, 5)
_MINUTES_RANGE = (10, 180)
_SUMMARY_MAX = 120

DEFAULT_BRIGHTNESS = 0.0
DEFAULT_START_ENERGY = 0.4
DEFAULT_STAGE_COUNT = 3

SYSTEM_PROMPT = (
    "너는 뱅드림(BanG Dream!) 음악 세트리스트 생성기의 무드 해석기다. "
    "사용자의 한국어/영어 자연어 요청을 읽고, 아래 JSON 스키마에 맞춰 "
    "무드·에너지 방향을 추출해 JSON 객체 하나로만 답한다. 코드블록·설명·군말 금지.\n"
    "**중요: 모든 파라미터를 요청 맥락에서 적극적·구체적으로 추론해 채워라. 애매하다고 기본값이나 "
    "null에 소극적으로 안주하지 말 것. 특히 재생시간(target_minutes)·단계 수(stage_count)를 활동/상황에 "
    "맞게 능동적으로 정하라. 각 값은 현실의 상식적 평균에 기반해 reasonable하게 산출한다(예: 5km 러닝은 "
    "보통 30~45분 걸리므로 40분 정도로).**\n\n"
    "필드:\n"
    "- brightness: -1.0(어두움)~+1.0(밝음) 실수. 밝고 기분 좋은 요청은 양수, 차분·어두운 요청은 음수.\n"
    "- start_energy: 0.0~1.0 실수. 세트리스트 시작 지점의 에너지. '조용/잔잔/차분/집중/수면' "
    "요청은 낮게(0.1~0.25), '신나는/파티/운동'은 높게(0.6~0.8).\n"
    "- end_energy: 0.0~1.0 실수. 마지막 지점의 에너지. **'점점 고조/build/올라가는' 같은 진행 "
    "요청이 명시될 때만** start보다 크게 한다. '조용/잔잔/차분' 처럼 전체 무드가 일정한 요청은 "
    "start와 거의 같게(플랫) 두어 끝까지 낮게 유지한다.\n"
    "- stage_count: 2~5 정수. 에너지 흐름의 굴곡 수에 맞춰 **능동적으로** 정하라(단순 상승/하강/일정=2~3, "
    "준비-본운동-정리처럼 오르내리는 활동=4~5). 무성의하게 항상 3만 쓰지 말 것.\n"
    "- stage_energies: (선택) 0.0~1.0 실수 배열(길이 2~5). 운동·유산소·러닝처럼 에너지가 오르내리는 "
    "활동은 **반드시** 자연스러운 아크를 단계별로 담아라. 예: 러닝=[0.3,0.7,0.85,0.5](준비→가속→유지→마무리), "
    "유산소=[0.3,0.85,0.85,0.4]. 주면 start_energy/end_energy/stage_count보다 우선한다. 단순 상승/하강/일정만 "
    "생략하고 start/end로.\n"
    "- target_minutes: 10~180 정수. 발화에 시간이 있으면 그대로. 없어도 **활동·상황이 암시하는 재생시간을 "
    "상식적 평균으로 reasonable하게 추정**해 넣어라(예: 5km 러닝≈40분, 공부 1세션≈50분, 낮잠≈20분, "
    "출퇴근≈40분, 파티≈120분). 정말 아무 단서도 없을 때만 null.\n"
    "- interpretation_summary: 이 플레이리스트의 분위기를 한 문장으로 따뜻하게 요약한 한국어 "
    "플레이버 텍스트(80자 이내). 숫자·수치(밝기 0.7 같은) 나열 금지, 감성적으로.\n"
    "- tags: 이 플레이리스트를 표현하는 인스타그램식 해시태그 키워드 배열(최대 5개, # 없이, "
    "한국어 짧은 단어). 예: [\"드라이브\",\"밝은\",\"설렘\"]. 억지로 다 채우지 말고 어울리는 만큼만.\n"
    "- song_type: \"all\" | \"original\" | \"cover\". 사용자가 '커버곡만/커버로'라 하면 \"cover\", "
    "'오리지널만/원곡만'이면 \"original\", 언급이 없으면 \"all\".\n"
    "- same_as_previous: 불리언. **직전 요청이 함께 제공된 경우에만** 의미가 있다. 직전 요청과 현재 "
    "요청이 본질적으로 같은 의도(같은 상황·목적, 표현·군더더기만 다름)면 true, 의도가 달라졌으면 false. "
    "직전 요청이 제공되지 않으면 false.\n\n"
    '예: {"brightness":0.7,"start_energy":0.35,"end_energy":0.85,"stage_count":3,'
    '"target_minutes":60,"interpretation_summary":"주말을 여는 설레는 드라이브, 점점 달아오르는 한 시간",'
    '"tags":["드라이브","설렘","주말","고조되는"],"song_type":"all","same_as_previous":false}'
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
                "target_minutes": {"type": ["integer", "null"]},
                "interpretation_summary": {"type": "string"},
                "tags": {"type": ["array", "null"], "items": {"type": "string"}},
                "song_type": {"type": "string", "enum": ["all", "original", "cover"]},
                "same_as_previous": {"type": "boolean"},
            },
            "required": [
                "brightness",
                "start_energy",
                "end_energy",
                "stage_count",
                "stage_energies",
                "target_minutes",
                "interpretation_summary",
                "tags",
                "song_type",
                "same_as_previous",
            ],
        },
    },
}


def build_messages(user_prompt: str, previous_prompt: str | None = None) -> list[dict]:
    """OpenRouter/Groq chat/completions messages 배열을 만든다.

    previous_prompt가 주어지면(2회차+ 요청) 직전 요청과 현재 요청을 함께 제시하고, 두 요청이
    '본질적으로 같은 의도'인지 same_as_previous로 판정하게 한다(핫픽스: 세부설정 우선순위 결정).
    파라미터는 항상 '현재 요청' 기준으로 산출한다.
    """
    if previous_prompt and previous_prompt.strip():
        user_content = (
            "아래는 직전 회차 요청과 현재 회차 요청이다. 두 요청이 본질적으로 같은 의도인지 판단해 "
            "same_as_previous(true/false)로 표기하라. 나머지 파라미터는 반드시 '현재 요청' 기준으로 산출한다.\n"
            f"[직전 요청]\n{previous_prompt.strip()}\n\n[현재 요청]\n{user_prompt}"
        )
    else:
        user_content = user_prompt
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
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

    tags = _clean_tags(obj.get("tags"))

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
