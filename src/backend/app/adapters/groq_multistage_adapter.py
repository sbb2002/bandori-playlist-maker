"""Groq 멀티스테이지 어댑터 — MoodInterpreter 포트의 실험적 구현(파일럿, feature test).

배경(topic/llm-param-control-separate/backgroud.md): 단일 LLM 요청 1회로 무드 파라미터
전체를 한 번에 뽑는 기존 `groq_adapter.GroqMoodInterpreter` 대신, 각 파라미터를 순서대로
LLM에 물어 JSON을 조립한다 — LLM 응답은 매번 숫자/짧은 텍스트뿐이라 관용 JSON 파서가 필요
없다("json 조립은 직접 파싱하기").

4단계 호출:
    1차 — 전체 재생시간(분, 정수).
    2차 — 구간 수(2~5)와 구간별 (길이(분), 감정 키워드).
    3차 — 구간별 감정 키워드를 보고 구간별 에너지(0.00~1.00).
    4차 — 위 결과(재생시간·구간별 무드·에너지)를 보고 요약 카드 한 문장(interpretation_summary).
          원래 의도가 이 필드도 LLM이 쓰게 하는 것이었어서(결정론적 조립 대신) 4차로 추가함.

스코프 결정(배경 문서에 없는 필드는 이 실험에서 다루지 않음, 확장은 별도 라운드):
    - brightness: 이 파이프라인엔 밝기 축 질문이 없다 → 중립값 0.0 고정.
    - song_type / same_as_previous: 배경 문서 미언급 → 기본값(all / None). same_as_previous가
      항상 None이므로 라우트의 `honor`는 이 인터프리터에서는 항상 False로 평가된다(세부설정
      override가 회차 간 유지되지 않음 — 실험 범위 밖의 알려진 제약).
    - tags: 4차에서 받은 것이 아니라 2차 감정 키워드를 그대로 재사용(ensure_min_tags로 최소
      2개 보장) — 별도 LLM 호출 없이 충분히 자연스러워 추가 비용을 들이지 않기로 함.
    - 2차에서 받은 구간별 '길이(분)'는 3차 프롬프트의 맥락으로만 쓰고, 최종 target_minutes는
      1차 값을 그대로 쓴다(도메인이 구간별 개별 길이를 지원하지 않고 stage_count로 균등분배하기
      때문 — `domain/selection.py`의 `_stage_targets_and_counts` 참고).

모델은 배경 문서 지정대로 `llama-3.1-8b-instant`(무료/저비용) 고정 기본값을 쓴다.
"""

from __future__ import annotations

import random
import re
import time

import httpx

from ..domain.models import MoodParameters
from ..domain.tags import ensure_min_tags
from ..ports.mood_port import (
    LLMRateLimitError,
    LLMUpstreamError,
    MoodInterpretationError,
)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_TIMEOUT = 60.0

_MINUTES_RANGE = (10, 180)
_STAGE_RANGE = (2, 5)
_ENERGY_RANGE = (0.0, 1.0)
_DEFAULT_MINUTES = 60
_DEFAULT_STAGE_COUNT = 3
_DEFAULT_MOOD = "평온"
_DEFAULT_ENERGY = 0.5
_SUMMARY_MAX = 120


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _after_marker(content: str, marker: str) -> str:
    """마커 뒤 텍스트만 반환. 마커가 없으면(모델이 지시를 어긴 경우) 전체 텍스트로 폴백."""
    idx = content.rfind(marker)
    if idx == -1:
        return content
    return content[idx + len(marker):]


def _ro_particle(word: str) -> str:
    """단어 끝음절 받침 유무로 '로'/'으로' 조사를 고른다(예: 긴장감→으로, 승리→로).

    한글 음절(U+AC00~U+D7A3)의 마지막 문자만 판단한다. 받침이 없거나 ㄹ받침이면 '로',
    그 외 받침이 있으면 '으로'. 한글이 아닌 문자로 끝나면(영문 등) 무난한 '로'로 폴백.
    """
    word = word.strip()
    if not word:
        return "로"
    last = word[-1]
    code = ord(last) - 0xAC00
    if not (0 <= code <= 11171):
        return "로"
    jong = code % 28
    return "로" if jong in (0, 8) else "으로"


class GroqMultistageMoodInterpreter:
    """3회 순차 Groq 호출로 무드를 해석하는 MoodInterpreter 구현(실험용)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        max_retries: int = 2,
        retry_base: float = 0.5,
        stage_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("Groq api_key가 비어 있습니다.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._max_retries = max(0, max_retries)
        self._retry_base = max(0.0, retry_base)
        # 각 단계(1~3차)별 파싱 실패 시 재호출 횟수(HTTP 재시도와 별개 — 응답은 200인데
        # 형식이 안 맞는 경우를 위함, groq_adapter.py의 mood_parse_retries와 동일한 목적).
        self._stage_retries = max(0, stage_retries)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """chat/completions 1회 호출 → content 문자열. 429/5xx는 백오프 재시도."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        url = f"{self._base_url}/chat/completions"
        headers = self._headers()
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, headers=headers, json=payload, timeout=self._timeout)
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    time.sleep(self._backoff(attempt))
                    continue
                raise LLMUpstreamError(f"Groq 요청 실패: {exc}") from exc

            if response.status_code == 200:
                try:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise MoodInterpretationError(f"Groq 응답 구조 예상 밖: {exc}") from exc
                if not isinstance(content, str) or not content.strip():
                    raise MoodInterpretationError("Groq 응답 content가 비어 있습니다.")
                return content.strip()

            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            if retryable and attempt < self._max_retries:
                time.sleep(self._retry_delay(response, attempt))
                continue

            body = response.text[:200]
            if response.status_code == 429:
                raise LLMRateLimitError(f"Groq 레이트리밋(429): {body}")
            raise LLMUpstreamError(f"Groq 비정상 응답 {response.status_code}: {body}")

        raise LLMUpstreamError("Groq 재시도 로직 예외(도달 불가)")

    def _backoff(self, attempt: int) -> float:
        return min(8.0, self._retry_base * (2**attempt)) + random.uniform(0.0, 0.3)

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except (TypeError, ValueError):
                pass
        return self._backoff(attempt)

    def _call_with_stage_retry(self, stage_name: str, call) -> object:
        """단계 1회 호출 결과를 `call`(파서)에 넘겨 파싱 실패 시 재호출."""
        last_error: MoodInterpretationError | None = None
        for _ in range(self._stage_retries + 1):
            try:
                return call()
            except MoodInterpretationError as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise MoodInterpretationError(f"[{stage_name}] {last_error}")

    # 무료 경량 모델(llama-3.1-8b-instant)은 "숫자만 답해" 지시를 자주 무시하고 장문
    # 설명을 덧붙인다(로컬 테스트에서 실측 확인 — 예: "5km 러닝을 위해..." 같은 서술 후 결론).
    # 그래서 프로덕션 groq_adapter.py의 관용 파싱 철학(전문 설명은 허용하고 최종 값만
    # 마커로 구분해 추출)을 그대로 따른다: 자유 서술은 허용하되 마지막에 반드시
    # `_ANSWER_MARKER` 뒤에 최종 값만 쓰게 하고, 마커를 못 찾으면 전체 텍스트에서 관용적으로
    # 재추출한다(첫 숫자가 아니라 "마지막" 숫자/줄 — 결론이 보통 끝에 오므로).
    _ANSWER_MARKER = "===ANSWER==="

    # ── 1차: 전체 재생시간(분) ──────────────────────────────────────────────
    _STAGE1_SYSTEM = (
        "너는 뱅드림(BanG Dream!) 세트리스트의 전체 재생시간을 정하는 보조자다. "
        "사용자 요청을 읽고 이 플레이리스트가 총 몇 분이면 좋을지 상식적으로 추정한다 "
        "(예: 5km 러닝은 보통 30~45분이니 40 정도).\n"
        f"생각 과정은 자유롭게 적어도 좋지만, 맨 마지막 줄에 반드시 정확히 "
        f"'{_ANSWER_MARKER}' 를 쓰고 그다음 줄에 정수(분) 하나만 적어라. 그 뒤에는 아무것도 "
        "쓰지 마라."
    )

    def _stage1_minutes(self, prompt: str) -> int:
        def parse() -> int:
            content = self._chat(self._STAGE1_SYSTEM, prompt)
            tail = _after_marker(content, self._ANSWER_MARKER)
            numbers = re.findall(r"-?\d+", tail)
            if not numbers:
                raise MoodInterpretationError(f"1차 응답에서 정수를 찾지 못함: {content[:150]!r}")
            # 마커를 찾았으면 그 뒤 첫 숫자, 못 찾아 전체 텍스트로 폴백했으면 결론이 보통
            # 끝에 오므로 마지막 숫자를 쓴다(첫 숫자는 "5km"처럼 요청 인용일 위험이 큼).
            value = numbers[0] if tail is not content else numbers[-1]
            return int(_clamp(int(value), *_MINUTES_RANGE))

        return self._call_with_stage_retry("1차/재생시간", parse)

    # ── 2차: 구간 수 + 구간별 (길이, 감정 키워드) ───────────────────────────
    _STAGE2_SYSTEM = (
        "너는 뱅드림 세트리스트의 구간(단계) 설계자다. 사용자 요청과 전체 재생시간(분)을 보고, "
        "전체를 2~5개 구간으로 나누고 각 구간의 길이(분)와 그 구간의 분위기를 나타내는 "
        "짧은 한국어 감정 키워드 하나를 정해라(예: 잔잔한, 고조되는, 신나는, 차분한). 구간 "
        "길이의 합은 전체 재생시간과 최대한 비슷하게 맞춘다.\n"
        f"생각 과정은 자유롭게 적어도 좋지만, 맨 마지막에 반드시 정확히 '{_ANSWER_MARKER}' 줄을 "
        "쓰고 그 다음부터 최종 답만 다음 형식으로 적어라(번호 매기지 말고 딱 이 형식만):\n"
        "첫 줄: 구간 수(정수) 하나만.\n"
        "그다음 줄부터 구간마다 한 줄씩 '길이(정수),감정키워드' 형식, 구간 순서대로.\n"
        f"예:\n{_ANSWER_MARKER}\n3\n15,잔잔한\n25,고조되는\n10,여운"
    )

    def _stage2_stages(self, prompt: str, target_minutes: int) -> list[tuple[int, str]]:
        def parse() -> list[tuple[int, str]]:
            user_prompt = f"[요청]\n{prompt}\n\n[전체 재생시간] {target_minutes}분"
            content = self._chat(self._STAGE2_SYSTEM, user_prompt)
            tail = _after_marker(content, self._ANSWER_MARKER)
            lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
            if not lines:
                raise MoodInterpretationError("2차 응답이 비어 있음")

            count_match = re.search(r"\d+", lines[0])
            if not count_match:
                raise MoodInterpretationError(f"2차 첫 줄에서 구간 수를 찾지 못함: {lines[0]!r}")
            declared_count = int(_clamp(int(count_match.group()), *_STAGE_RANGE))

            stages: list[tuple[int, str]] = []
            for line in lines[1:]:
                if "," not in line:
                    continue
                length_str, mood_str = line.split(",", 1)
                # 모델이 번호("1. 15")를 덧붙여도 실제 길이는 마지막 숫자이므로 rfind로 취한다.
                length_matches = re.findall(r"\d+", length_str)
                length = int(length_matches[-1]) if length_matches else 1
                mood = mood_str.strip().lstrip("#").strip() or _DEFAULT_MOOD
                stages.append((max(1, length), mood))
                if len(stages) >= declared_count:
                    break

            if len(stages) < 2:
                raise MoodInterpretationError(f"2차 응답에서 구간을 2개 이상 파싱하지 못함: {lines!r}")

            # 실제로 파싱된 구간 수를 우선(모델이 선언한 stage_count와 어긋나면 파싱 결과를 신뢰).
            stages = stages[:_STAGE_RANGE[1]]
            if len(stages) < _STAGE_RANGE[0]:
                raise MoodInterpretationError("2차 응답 구간 수가 최소치 미만")
            return stages

        return self._call_with_stage_retry("2차/구간분할", parse)

    # ── 3차: 구간별 에너지 ───────────────────────────────────────────────
    _STAGE3_SYSTEM = (
        "너는 뱅드림 세트리스트의 구간별 에너지(강도)를 정하는 보조자다. 순서대로 나열된 "
        "구간별 감정 키워드를 보고, 각 구간의 에너지를 0.00(아주 잔잔함)~1.00(아주 신남) 사이 "
        "소수 둘째자리까지의 실수로 정해라.\n"
        f"생각 과정은 자유롭게 적어도 좋지만, 맨 마지막에 반드시 정확히 '{_ANSWER_MARKER}' 줄을 "
        "쓰고 그 다음부터 구간 순서대로 한 줄에 숫자 하나씩만 적어라(번호·설명 없이 숫자만, "
        "줄 수는 구간 수와 정확히 같게).\n"
        f"예(구간 3개):\n{_ANSWER_MARKER}\n0.25\n0.70\n0.40"
    )

    def _stage3_energies(self, moods: list[str]) -> list[float]:
        def parse() -> list[float]:
            listing = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(moods))
            content = self._chat(self._STAGE3_SYSTEM, listing)
            tail = _after_marker(content, self._ANSWER_MARKER)
            lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
            # 줄마다 "마지막" 숫자만 취한다 — 모델이 "1. 0.75"처럼 번호를 덧붙여도 실제 값은
            # 그 줄의 마지막 숫자이므로(맨 앞 "1"을 값으로 오인하는 사고를 방지).
            energies: list[float] = []
            for line in lines:
                nums = re.findall(r"\d*\.\d+|\d+", line)
                if nums:
                    energies.append(_clamp(float(nums[-1]), *_ENERGY_RANGE))
            if len(energies) < len(moods):
                raise MoodInterpretationError(
                    f"3차 응답 개수 부족(필요 {len(moods)}, 파싱 {len(energies)}): {content[:150]!r}"
                )
            return energies[: len(moods)]

        return self._call_with_stage_retry("3차/구간에너지", parse)

    # ── 4차: 요약 카드 문장(interpretation_summary) ─────────────────────────
    # 원래 의도가 이 필드도 LLM이 쓰게 하는 것이었다(결정론적 문장 조립 대신). 다만 요약
    # 문구는 세트리스트 조립에 필수 입력이 아니라 UI 장식용이라, 4차가 실패해도 전체
    # interpret()을 실패시키지 않고 결정론적 폴백 문장(_fallback_summary)으로 내려간다.
    _STAGE4_SYSTEM = (
        "너는 뱅드림(BanG Dream!) 세트리스트 요약 카드에 들어갈 문구를 쓰는 보조자다. "
        "주어진 재생시간·구간별 분위기·에너지 흐름을 보고, 이 플레이리스트의 분위기를 "
        "따뜻하고 감성적인 한국어 한 문장으로 요약해라(80자 이내). 숫자·수치(에너지 0.7 같은) "
        "나열 금지, 코드블록·따옴표 금지.\n"
        f"생각 과정은 자유롭게 적어도 좋지만, 맨 마지막에 반드시 정확히 '{_ANSWER_MARKER}' 줄을 "
        "쓰고 그다음 줄에 완성된 요약 문장 하나만 적어라(그 뒤엔 아무것도 쓰지 마라)."
    )

    def _stage4_summary(
        self, prompt: str, moods: list[str], energies: list[float], target_minutes: int
    ) -> str:
        fallback = self._fallback_summary(moods)

        def parse() -> str:
            arc = ", ".join(f"{m}({e:.2f})" for m, e in zip(moods, energies))
            user_prompt = f"[요청]\n{prompt}\n\n[재생시간] {target_minutes}분\n[구간 흐름] {arc}"
            content = self._chat(self._STAGE4_SYSTEM, user_prompt)
            tail = _after_marker(content, self._ANSWER_MARKER)
            lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
            if not lines:
                raise MoodInterpretationError(f"4차 응답에서 요약 문장을 찾지 못함: {content[:150]!r}")
            return lines[0].strip('"\'`')[:_SUMMARY_MAX]

        try:
            return self._call_with_stage_retry("4차/요약", parse)
        except MoodInterpretationError:
            # 요약은 UI 장식용이라 실패해도 세트리스트 생성 자체를 막지 않는다 — 결정론적
            # 문장으로 안전하게 폴백(§4차 docstring 참고).
            return fallback

    def _fallback_summary(self, moods: list[str]) -> str:
        return (
            f"{moods[0]}{_ro_particle(moods[0])} 시작해 "
            f"{moods[-1]}{_ro_particle(moods[-1])} 이어지는 {len(moods)}단계 흐름"
        )

    def interpret(self, prompt: str, previous_prompt: str | None = None) -> MoodParameters:
        target_minutes = self._stage1_minutes(prompt)
        stages = self._stage2_stages(prompt, target_minutes)
        moods = [m for _length, m in stages]
        energies = self._stage3_energies(moods)
        summary = self._stage4_summary(prompt, moods, energies, target_minutes)

        stage_count = len(stages)
        start_energy = energies[0]
        end_energy = energies[-1]
        tags = ensure_min_tags(list(dict.fromkeys(moods))[:5], 0.0, start_energy, end_energy, target_minutes)

        return MoodParameters(
            brightness=0.0,
            start_energy=start_energy,
            end_energy=end_energy,
            stage_count=stage_count,
            target_minutes=target_minutes,
            interpretation_summary=summary[:120],
            stage_energies=energies,
            tags=tags,
            song_type="all",
            same_as_previous=None,
        )
