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
# 3단계: MoodParameters.stage_params 항목의 키(StageSpec/Stage와 동일 이름, 전부 0.0~1.0).
_STAGE_PARAM_KEYS = (
    "valence", "lufs_integrated", "lra",
    "danceability_norm", "instr_stem_ratio", "speech_median",
)

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
    "- stage_minutes: **반드시** 길이가 stage_count와 정확히 같은 실수 배열로 채워라(stage_params와 "
    "마찬가지로 비워도 되는 선택 필드가 아니다 — null 금지). 합계는 target_minutes와 대략 같아야 "
    "한다. **사용자가 특정 구간의 길이를 명시/암시하면(예: '마지막 5분은 릴랙스', '초반 10분 "
    "워밍업만 짧게', '마지막에 차분한 구간을 길게') 그 구간만 다른 길이로 반드시 반영하라** — "
    "균등분배(전 구간 동일 길이)로 뭉개면 안 된다. 예: 러닝(60분, 4단계, 마지막은 정리운동으로 "
    "짧게)이면 [15,20,15,10]. 구간 길이에 대한 언급이 전혀 없으면 target_minutes를 stage_count로 "
    "균등하게 나눈 값을 그대로 배열로 채운다(예: 40분 5단계면 [8,8,8,8,8]) — 이 경우에도 배열 "
    "자체는 반드시 채우고 null을 반환하지 말 것.\n"
    "- target_minutes: 10~180 정수. 발화에 시간이 있으면 그대로. 없어도 **활동·상황이 암시하는 재생시간을 "
    "상식적 평균으로 reasonable하게 추정**해 넣어라(예: 5km 러닝≈40분, 공부 1세션≈50분, 낮잠≈20분, "
    "출퇴근≈40분, 파티≈120분). 정말 아무 단서도 없을 때만 null.\n"
    "- interpretation_summary: 이 플레이리스트의 분위기를 한 문장으로 따뜻하게 요약한 한국어 "
    "플레이버 텍스트(80자 이내). 숫자·수치(밝기 0.7 같은) 나열 금지, 감성적으로.\n"
    "- tags: 이 플레이리스트를 표현하는 인스타그램식 해시태그 키워드 배열(**반드시 2~5개**, "
    "# 없이, 한국어 짧은 단어). interpretation_summary의 분위기를 대표하는 핵심 키워드로 채운다. "
    "예: [\"드라이브\",\"밝은\",\"설렘\"]. **절대 비우지 말 것 — 최소 2개는 필수.**\n"
    "- song_type: \"all\" | \"original\" | \"cover\". 사용자가 '커버곡만/커버로'라 하면 \"cover\", "
    "'오리지널만/원곡만'이면 \"original\", 언급이 없으면 \"all\".\n"
    "- same_as_previous: 불리언. **직전 요청이 함께 제공된 경우에만** 의미가 있다. 직전 요청과 현재 "
    "요청이 본질적으로 같은 의도(같은 상황·목적, 표현·군더더기만 다름)면 true, 의도가 달라졌으면 false. "
    "직전 요청이 제공되지 않으면 false.\n"
    "- stage_params: **반드시** 길이가 stage_count와 정확히 같은 객체 배열로 채워라(brightness/"
    "start_energy와 마찬가지로 요청 맥락에서 적극적으로 추론 — 비워도 되는 선택 필드가 아니다). "
    "각 객체는 그 단계의 음향 성격을 0.0~1.0 실수 6개로 나타낸다:\n"
    "  · valence: 정서 밝기(낮음=무겁고 어두운 느낌, 높음=밝고 화사한 느낌). brightness와 같은 방향.\n"
    "  · lufs_integrated: 체감 라우드니스(낮음=조용/절제된 소리, 높음=크고 꽉 찬 소리). energy와 비슷하게 움직임.\n"
    "  · lra: 다이내믹 범위(낮음=음량이 일정, 높음=조용한 부분과 큰 부분 격차가 큼). 발라드·클래식풍은 높게, "
    "일렉트로닉/파티는 낮게.\n"
    "  · danceability_norm: 리듬감(낮음=리듬이 불규칙/약함, 높음=규칙적이고 춤추기 좋음). energy와 비슷하게 움직임.\n"
    "  · instr_stem_ratio: 악기 비중(낮음=보컬 위주, 높음=연주/악기 비중이 큼). 특별한 언급 없으면 "
    "[지표 분포 통계]의 median 부근.\n"
    "  · speech_median: 가사 밀도(낮음=여백이 많고 느긋한 가창, 높음=가사가 빽빽하고 빠른 딕션). 랩/힙합은 높게, "
    "발라드는 낮게, 특별한 언급 없으면 [지표 분포 통계]의 median 부근.\n"
    "  시스템 메시지 끝에 [지표 분포 통계](후보 곡 풀의 전체·밴드별 min/max/mean/median/std, 같은 스케일)가 "
    "제공되면 **각 값을 반드시 그 분포에 근거해 골라라**: 의도한 무드가 분포에서 어느 위치인지 짚어, 낮추려면 "
    "min~median 사이, 높이려면 median~max 사이의 실제로 구분되는 값을 쓴다. 특정 밴드 위주 요청이면 그 밴드 "
    "행을 우선 참고. 분포를 무시한 관성적 0.5 금지.\n"
    "  6개 키 전부 채워라(정말 판단 근거가 없는 키만 예외적으로 생략).\n"
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
                        },
                        "required": [
                            "valence", "lufs_integrated", "lra",
                            "danceability_norm", "instr_stem_ratio", "speech_median",
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
            row: dict[str, float | None] = {}
            for key in _STAGE_PARAM_KEYS:
                v = entry.get(key)
                if v is None:
                    row[key] = None
                    continue
                try:
                    row[key] = _clamp(float(v), *_ENERGY_RANGE)
                except (TypeError, ValueError):
                    row[key] = None
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
