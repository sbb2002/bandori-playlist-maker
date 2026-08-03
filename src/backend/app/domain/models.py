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
    # 오디오 지표 6종(연구 채택 파라미터, CSV m*-컬럼) — eligible 풀 기준 minmax 스케일 0~1.
    # UI 슬라이더·LLM stage_params와 동일 스케일. 컬럼이 없는 CSV(구 스냅샷)에서는 None.
    valence: float | None = None
    lufs_integrated: float | None = None
    lra: float | None = None
    danceability_norm: float | None = None
    instr_stem_ratio: float | None = None
    speech_median: float | None = None
    # 검색 보조용(원문 CSV엔 없음 — song_repo가 로드 시 pykakasi/hanja로 1회 계산해 캐싱).
    # 일본어를 모르는 사용자가 '곡 추가' 미니 브라우저에서 검색할 수 있도록 로마자/한글 음차 제공.
    song_romaji: str = ""
    song_hangul: str = ""
    song_hangul_search: str = ""  # 한글 음차 변형 병기(" / " 연결, 검색 매칭 전용 — 표시 안 함)
    song_hanja_reading: str = ""  # 한자 → 한국 한자음(음독)


@dataclass(frozen=True)
class MoodParameters:
    """스키마1 — LLM 출력(검증·클램프·기본값 주입 완료). 도메인은 항상 유효 값만 수신."""

    brightness: float          # -1.0(어두움) ~ +1.0(밝음)
    start_energy: float        # 0.0 ~ 1.0
    end_energy: float          # 0.0 ~ 1.0
    stage_count: int           # 2 ~ 5
    target_minutes: int | None # 10 ~ 180, 또는 None(API가 60 적용)
    interpretation_summary: str = ""
    # 단계별 에너지 목표(비단조 아크 지원 — 유산소=준비↓→본운동↑→정리↓ 등). 주어지면
    # start/end/stage_count 대신 이 배열을 단계 목표로 쓴다(선형 보간 불필요). None이면 선형 아크.
    stage_energies: list[float] | None = None
    # 인스타그램식 해시태그 키워드(# 없이, 2~5개). 요약 카드에 감성 태그로 표시.
    # 어댑터가 domain/tags.ensure_min_tags로 최소 2개를 보장한다(LLM이 비워도 파생 보충).
    tags: list[str] | None = None
    # 곡 종류 필터 의도: "all" | "original" | "cover". 사용자가 커버/오리지널만 원하면 그에 맞게,
    # 아니면 "all". 사용자가 체크박스를 명시하면 그게 우선(라우트에서 조정).
    song_type: str = "all"
    # DEPRECATED(2026-08-03, 3단계): AI 모드/커스텀 모드가 명확히 분리되면서(AI=항상 LLM이
    # 새로 해석, 커스텀=항상 사용자 설정 그대로) "직전 요청과 의도가 같은가"를 판정해 세부설정
    # override 여부를 가르던 이 메커니즘 자체가 불필요해졌다 — 라우트는 이제 payload.mode만
    # 보고 honor를 정한다(routes.py 참고). 필드는 하위호환을 위해 유지하되 더 이상 라우팅에
    # 쓰이지 않는다. 삭제하지 말 것(다른 로컬/세션이 참조 중일 수 있음).
    same_as_previous: bool | None = None
    # 3단계: LLM이 AI 모드 단일 응답으로 단계별 6개 신규 오디오 파라미터를 함께 채운 값(선택).
    # 길이는 stage_count와 같아야 하며, 각 dict의 키는 StageSpec/Stage와 동일: valence·
    # lufs_integrated·lra·danceability_norm·instr_stem_ratio·speech_median(전부 0.0~1.0,
    # 개별 키가 없거나 None이면 그 값만 미상). selection.py가 stage_specs 없을 때(AI 모드
    # 첫 요청 등) 이 값을 Stage에 반영한다 — 선곡 매칭 가중치엔 아직 안 씀(echo 전용, 2단계
    # "배관만" 결정 계승).
    stage_params: list[dict[str, float | None]] | None = None
    # 3.5단계: 단계별 길이(분) 의도(선택). 주어지면(길이==stage_count) 곡 수를 균등분배 대신
    # 이 분 비율로 배분한다(selection.py의 _stage_targets_and_counts) — "마지막 5분은
    # 릴랙스"처럼 특정 구간만 짧게/길게 요청한 의도가 곡 개수에도 반영되도록. None이면 기존
    # 균등분배(distribute_counts) 그대로 — 하위호환.
    stage_minutes: list[float] | None = None


@dataclass(frozen=True)
class Stage:
    """세트리스트의 시간축 단계 1개."""

    index: int
    energy_target: float
    valence: float | None = None
    lufs_integrated: float | None = None
    lra: float | None = None
    danceability_norm: float | None = None
    instr_stem_ratio: float | None = None
    speech_median: float | None = None
    # TODO(data-pipeline): songs_master.csv에 컬럼 추가 후 domain/selection.py 매칭에 반영


@dataclass(frozen=True)
class StageSpec:
    """사용자가 직접 지정한 단계 스펙(설정 기능, PRD §5-1a).

    선곡 엔진에 넘기면 LLM 유도 에너지 아크 대신 이 값으로 단계를 강제한다.
    `song_count`는 곡 수(시간 지정은 API에서 곡 수로 환산해 넘긴다).
    """

    energy_target: float   # 0.0 ~ 1.0
    song_count: int        # >= 1
    valence: float | None = None
    lufs_integrated: float | None = None
    lra: float | None = None
    danceability_norm: float | None = None
    instr_stem_ratio: float | None = None
    speech_median: float | None = None
    # TODO(data-pipeline): songs_master.csv에 컬럼 추가 후 domain/selection.py 매칭에 반영


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
    # 후보 풀 부족으로 허용창(_TOL) 밖 곡이 불가피하게 선택됐는지(hotfix: 4-5단계 사이 완충 노드).
    # True면 이 곡의 energy가 stage_energy_target에서 _TOL을 넘겨 벗어났다는 뜻.
    degraded: bool = False


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
