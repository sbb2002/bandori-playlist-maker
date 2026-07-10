"""API 요청/응답 DTO (스키마3 — architecture.md §③).

요청은 pydantic으로 검증하고, 응답은 도메인 Setlist를 평범한 dict로 직렬화한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..domain.models import Setlist


class SetlistRequest(BaseModel):
    """POST /api/setlist 요청 바디."""

    prompt: str = Field(..., min_length=1, max_length=500, description="자연어 요청 한 문장")
    target_minutes: int | None = Field(default=None, ge=10, le=180, description="목표 재생시간(분)")
    stage_count: int | None = Field(default=None, ge=2, le=5, description="에너지 단계 수 N")

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
