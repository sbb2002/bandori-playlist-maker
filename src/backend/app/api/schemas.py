"""API 요청/응답 DTO (스키마3 — architecture.md §③).

요청은 pydantic으로 검증하고, 응답은 도메인 Setlist를 평범한 dict로 직렬화한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..domain.models import Setlist


class StageInput(BaseModel):
    """사용자 지정 단계 1개(설정 기능 §5-1a). 에너지 + (시간 또는 곡 수) 중 최소 1개."""

    energy: float = Field(..., ge=0.0, le=1.0, description="이 단계의 에너지 레벨 0~1")
    minutes: int | None = Field(default=None, ge=1, le=180, description="이 단계 지정 시간(분)")
    song_count: int | None = Field(default=None, ge=1, le=60, description="이 단계 곡 수")
    valence: float | None = Field(default=None, ge=0.0, le=1.0, description="밝기 지표 0~1")
    lufs_integrated: float | None = Field(default=None, description="통합 라우드니스(LUFS)")
    lra: float | None = Field(default=None, description="다이나믹 범위(LRA, dB)")
    danceability_norm: float | None = Field(default=None, ge=0.0, le=1.0, description="리듬감 0~1")
    instr_stem_ratio: float | None = Field(default=None, ge=0.0, le=1.0, description="악기 비율 0~1")
    speech_median: float | None = Field(default=None, ge=0.0, le=1.0, description="음절 밀도 0~1")
    # 프로토타입: 커스텀 모드에서 사용자가 직접 입력하는 가사 감상(선택). 비우면 기존과 동일하게
    # 가사 유사도 타이브레이크가 중립(비활성) 처리된다.
    impression: str | None = Field(default=None, max_length=100, description="이 단계의 가사 감상(선택)")
    # 프로토타입: 커스텀 모드에서 이 단계를 특정 밴드 목록으로만 고정(선택, 1개 이상 동시
    # 지정 가능). songs_master.csv의 band 값이어야 하며, 아니면 selection.py에서 후보가
    # 0건이 돼 그 슬롯이 자동으로 건너뛰어진다(검증은 라우트가 아니라 도메인의 자연스러운
    # 결과에 맡김 — AI 모드 stage_bands와 달리 사용자가 팝업에서 직접 고르므로 오탈자·
    # 할루시네이션 걱정이 없다). 빈 배열/None = 제한 없음(전역 밴드 필터만 적용).
    bands: list[str] | None = Field(default=None, description="이 단계를 고정할 밴드 목록(선택)")

    @field_validator("impression")
    @classmethod
    def _blank_impression_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _require_size(self) -> "StageInput":
        if self.minutes is None and self.song_count is None:
            raise ValueError("각 단계는 minutes 또는 song_count 중 하나는 지정해야 합니다.")
        return self


class SetlistRequest(BaseModel):
    """POST /api/setlist 요청 바디."""

    prompt: str | None = Field(default=None, max_length=500, description="자연어 요청 한 문장(AI 모드 필수)")
    mode: Literal["ai", "custom"] = Field(default="ai", description="AI 모드(LLM) 또는 커스텀 모드(수동 설정)")
    # 직전 회차 요청(2회차+). 주어지면 백엔드가 LLM에 함께 넘겨 '의도가 같은지'를 판정하고,
    # 같을 때만 아래 사용자 override(target_minutes·stage_count·stages·bands·cover)를 적용한다.
    previous_prompt: str | None = Field(default=None, max_length=500, description="직전 회차 요청(의도 동일성 판정용)")
    target_minutes: int | None = Field(default=None, ge=10, le=180, description="목표 재생시간(분)")
    stage_count: int | None = Field(default=None, ge=2, le=11, description="에너지 단계 수 N")
    bands: list[str] | None = Field(default=None, max_length=50, description="밴드 필터(빈 목록/미지정=ALL)")
    stages: list[StageInput] | None = Field(default=None, min_length=1, max_length=11, description="단계 직접 지정(그래프 수동, 최대 11구간)")
    # None = 사용자가 체크박스를 안 건드림 → LLM의 song_type으로 결정(둘 다 미지정=ALL 기본).
    # 명시 시(둘 다) 그 값이 우선. 둘 다 같으면(모두 포함/모두 제외) ALL.
    include_original: bool | None = Field(default=None, description="오리지널 포함(None=LLM 판단)")
    include_cover: bool | None = Field(default=None, description="커버 포함(None=LLM 판단)")

    @model_validator(mode="after")
    def _validate_prompt(self) -> "SetlistRequest":
        # AI 모드에서만 prompt 필수
        if self.mode == "ai":
            if self.prompt is None:
                raise ValueError("AI 모드에서는 prompt가 필수입니다.")
            prompt_stripped = self.prompt.strip()
            if not prompt_stripped:
                raise ValueError("prompt는 공백만으로 구성될 수 없습니다.")
            self.prompt = prompt_stripped
        return self


def serialize_setlist(setlist: Setlist) -> dict:
    """도메인 Setlist를 API 응답 JSON(dict)으로 변환한다."""
    return {
        "params": {
            "brightness": setlist.params.brightness,
            "start_energy": setlist.params.start_energy,
            "end_energy": setlist.params.end_energy,
            "stage_count": setlist.params.stage_count,
            "target_minutes": setlist.params.target_minutes,
            "interpretation_summary": setlist.params.interpretation_summary,
            "tags": setlist.params.tags or [],
            "song_type": setlist.params.song_type,
            # 디버그 전용 노출(일반 UI는 안 읽음, "현재 상태 복사" 스냅샷용) — AI가 실제로
            # 산출한 원시 파라미터를 빠짐없이 확인하려는 목적. stage_params(6개 수치+
            # impression)는 이미 stages[]에 스테이지별로 echo되므로 여기선 생략.
            "stage_energies": setlist.params.stage_energies,
            "stage_minutes": setlist.params.stage_minutes,
            "same_as_previous": setlist.params.same_as_previous,
        },
        "stages": [
            {
                "index": s.index,
                "energy_target": s.energy_target,
                "valence": s.valence,
                "lufs_integrated": s.lufs_integrated,
                "lra": s.lra,
                "danceability_norm": s.danceability_norm,
                "instr_stem_ratio": s.instr_stem_ratio,
                "speech_median": s.speech_median,
                "impression": s.impression,
                "bands": list(s.bands) if s.bands else None,
            }
            for s in setlist.stages
        ],
        "estimated_total_seconds": setlist.estimated_total_seconds,
        "picks": [
            {
                "position": p.position,
                "idx": p.idx,
                "video_id": p.video_id,
                "band": p.band,
                "song": p.song,
                "camelot": p.camelot,
                "energy": p.energy,
                "stage_index": p.stage_index,
                "valence": p.valence,
                "lufs_integrated": p.lufs_integrated,
                "lra": p.lra,
                "danceability_norm": p.danceability_norm,
                "instr_stem_ratio": p.instr_stem_ratio,
                "speech_median": p.speech_median,
                "reason": {
                    "stage_energy_target": p.reason.stage_energy_target,
                    "matched_energy": p.reason.matched_energy,
                    "harmonic": p.reason.harmonic,
                    "prev_camelot": p.reason.prev_camelot,
                    "brightness_fit": p.reason.brightness_fit,
                    "text": p.reason.text,
                    "degraded": p.reason.degraded,
                },
            }
            for p in setlist.picks
        ],
    }
