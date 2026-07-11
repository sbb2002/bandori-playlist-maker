"""도메인 모델 (스키마1·스키마2 — architecture.md §③ 동결).

외부 의존 없음. pydantic·HTTP 금지. 표준 라이브러리 dataclass만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Song:
    """선곡 엔진이 소비하는 곡 1건. `data/songs_master.csv` 1행에 대응.

    파일럿 사용 컬럼(architecture.md §③ 스키마2):
        idx, band, song, video_id, camelot, energy(0–1), mode_score, shape, eligible_band.
    `duration_sec`은 향후 YouTube Data API 백필용(현재 전곡 None) — 있으면 실측 사이징.
    """

    idx: int
    band: str
    song: str
    video_id: str
    camelot: str
    energy: float
    mode_score: float
    shape: str
    eligible_band: bool
    duration_sec: int | None = None
    # 곡 경계 텐션(전곡 프레임별 강도의 인트로 0~15s / 아웃트로 last-15s 평균; i_* 동일 스케일).
    # 시퀀싱에서 이전 곡 아웃트로 ↔ 다음 곡 인트로를 매끄럽게 잇는 데 쓴다.
    intro_energy: float = 0.0
    outro_energy: float = 0.0


@dataclass(frozen=True)
class MoodParameters:
    """스키마1 — LLM 출력(검증·클램프·기본값 주입 완료). 도메인은 항상 유효 값만 수신."""

    brightness: float          # -1.0(어두움) ~ +1.0(밝음)
    start_energy: float        # 0.0 ~ 1.0
    end_energy: float          # 0.0 ~ 1.0
    stage_count: int           # 2 ~ 5
    target_minutes: int | None # 10 ~ 180, 또는 None(API가 60 적용)
    interpretation_summary: str = ""


@dataclass(frozen=True)
class Stage:
    """세트리스트의 시간축 단계 1개."""

    index: int
    energy_target: float


@dataclass(frozen=True)
class StageSpec:
    """사용자가 직접 지정한 단계 스펙(설정 기능, PRD §5-1a).

    선곡 엔진에 넘기면 LLM 유도 에너지 아크 대신 이 값으로 단계를 강제한다.
    `song_count`는 곡 수(시간 지정은 API에서 곡 수로 환산해 넘긴다).
    """

    energy_target: float   # 0.0 ~ 1.0
    song_count: int        # >= 1


@dataclass(frozen=True)
class PickReason:
    """선곡 이유 메타(architecture.md §③ 스키마2 · §④-4 '이유 노출 YES').

    엔진이 LLM 비용 0으로 생성. API는 항상 포함하고 프론트가 표시 강도를 조절한다.
    """

    stage_energy_target: float
    matched_energy: float
    harmonic: str              # "seed" | "same" | "adjacent" | "non_harmonic"
    prev_camelot: str | None
    brightness_fit: float      # 0.0~1.0 (1=밝기 목표와 완전 일치)
    text: str


@dataclass(frozen=True)
class Pick:
    """세트리스트 내 곡 1개(순서 포함)."""

    position: int
    idx: int
    video_id: str
    band: str
    song: str
    camelot: str
    energy: float
    stage_index: int
    reason: PickReason


@dataclass(frozen=True)
class Setlist:
    """선곡 엔진 출력(스키마2). `params` 에코 + 단계 + 추정 총재생시간 + 곡 순서."""

    params: MoodParameters
    stages: list[Stage]
    estimated_total_seconds: int
    picks: list[Pick] = field(default_factory=list)


class NoSetlistError(Exception):
    """세트리스트를 구성할 수 없음(후보곡 0건 등). API에서 409 NO_SETLIST로 매핑."""
