"""API 요청/응답 DTO (스키마3 — architecture.md §③).

요청은 pydantic으로 검증하고, 응답은 도메인 Setlist를 평범한 dict로 직렬화한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ..domain.models import Setlist


class StageInput(BaseModel):
    """사용자 지정 단계 1개(설정 기능 §5-1a). 에너지 + (시간 또는 곡 수) 중 최소 1개."""

    energy: float = Field(..., ge=0.0, le=1.0, description="이 단계의 에너지 레벨 0~1")
    minutes: int | None = Field(default=None, ge=1, le=180, description="이 단계 지정 시간(분)")
    song_count: int | None = Field(default=None, ge=1, le=60, description="이 단계 곡 수")

    @model_validator(mode="after")
    def _require_size(self) -> "StageInput":
        if self.minutes is None and self.song_count is None:
            raise ValueError("각 단계는 minutes 또는 song_count 중 하나는 지정해야 합니다.")
        return self


class SetlistRequest(BaseModel):
    """POST /api/setlist 요청 바디."""

    prompt: str = Field(..., min_length=1, max_length=500, description="자연어 요청 한 문장")
    target_minutes: int | None = Field(default=None, ge=10, le=180, description="목표 재생시간(분)")
    stage_count: int | None = Field(default=None, ge=2, le=5, description="에너지 단계 수 N")
    bands: list[str] | None = Field(default=None, max_length=50, description="밴드 필터(빈 목록/미지정=ALL)")
    stages: list[StageInput] | None = Field(default=None, min_length=1, max_length=11, description="단계 직접 지정(그래프 편집 시 최대 11구간=분리선 10개)")
    # None = 사용자가 체크박스를 안 건드림 → LLM의 song_type으로 결정(둘 다 미지정=ALL 기본).
    # 명시 시(둘 다) 그 값이 우선. 둘 다 같으면(모두 포함/모두 제외) ALL.
    include_original: bool | None = Field(default=None, description="오리지널 포함(None=LLM 판단)")
    include_cover: bool | None = Field(default=None, description="커버 포함(None=LLM 판단)")

    @field_validator("prompt")
    @classmethod
    def _strip_prompt(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt는 공백만으로 구성될 수 없습니다.")
        return v


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
        },
        "stages": [
            {"index": s.index, "energy_target": s.energy_target} for s in setlist.stages
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
                "reason": {
                    "stage_energy_target": p.reason.stage_energy_target,
                    "matched_energy": p.reason.matched_energy,
                    "harmonic": p.reason.harmonic,
                    "prev_camelot": p.reason.prev_camelot,
                    "brightness_fit": p.reason.brightness_fit,
                    "text": p.reason.text,
                },
            }
            for p in setlist.picks
        ],
    }
