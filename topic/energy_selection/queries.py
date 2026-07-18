"""
Queryset for energy_selection experiment.

DESIGN.md §3: 10 queries across 4 categories (A/B/C/D) with expected shapes and magnitude thresholds.
"""

# DESIGN.md §3 table, directly mapped
QUERIES = {
    # Category A: 양자택일/대조 (신규 실패모드)
    "A1": {
        "text": "장마철 꿉꿉한 기분을 날려줄 노래 아니면 습기에 젖는 서정적인 노래로 부탁해.",
        "category": "A",
        "expected_shape": "flat",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {},  # flat 허용폭(max-min≤0.15)만 검증, 절대값 제약 없음
    },
    "A2": {
        "text": "신나게 달리고 싶은 기분 아니면 조용히 가라앉고 싶은 기분, 아무거나 괜찮아.",
        "category": "A",
        "expected_shape": "flat",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {},
    },
    "A3": {
        "text": "밝은 곡이든 어두운 곡이든 상관없고 그냥 카페에서 틀어놓을 잔잔한 느낌으로.",
        "category": "A",
        "expected_shape": "flat",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"all_below": 0.35},  # 잔잔 → 전체 낮음
    },
    # Category B: 절대시간 피크지정 (신규 실패모드)
    "B1": {
        "text": "천천히 워밍업해서 30분즈음에 최고조에 달하게 해주고 그 뒤에 40분까지 마무리하도록 쿨다운하게 도와줘",
        "category": "B",
        "expected_shape": "peak",
        "target_minutes": 40,
        "peak_minute": 30,
        "magnitude_checks": {
            "peak_above": 0.65,  # 최고조 값 ≥0.65
            "first_below": 0.35,  # 워밍업 시작값 ≤0.35
        },
    },
    "B2": {
        "text": "20분짜리 짧은 운동인데 처음 5분은 몸 풀고 그 다음 쭉 강하게 가다가 마지막 3분만 정리해줘.",
        "category": "B",
        "expected_shape": "peak",
        "target_minutes": 20,
        "peak_minute": 12,  # 5분(0.25) ~ 17분(0.85) 중간 추정
        "magnitude_checks": {
            "peak_above": 0.65,
            "first_below": 0.40,  # 몸 풀기 = 낮은 시작
        },
    },
    "B3": {
        "text": "1시간짜리 파티인데 시작 10분은 분위기 띄우면서 살살, 15분쯤부터 45분까지는 계속 터지게, 마지막 15분은 여운 남게 잔잔히.",
        "category": "B",
        "expected_shape": "peak",
        "target_minutes": 60,
        "peak_minute": 30,  # 15분(0.25) ~ 45분(0.75) 중간
        "magnitude_checks": {
            "peak_above": 0.70,  # 고원형 파티 → 좀 더 높음
            "first_below": 0.35,  # 살살 띄우기
        },
    },
    # Category C: 회귀(기존 정상 케이스)
    "C1": {
        "text": "조용하고 잔잔한 노래로만 부탁해.",
        "category": "C",
        "expected_shape": "flat",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"all_below": 0.35},  # 조용하고 잔잔 → 전체 낮음
    },
    "C2": {
        "text": "신나는 파티 노래 위주로 틀어줘.",
        "category": "C",
        "expected_shape": "flat",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"all_above": 0.60},  # 신나는 파티 → 전체 높음
    },
    "C3": {
        "text": "천천히 시작해서 점점 신나지는 드라이브 플레이리스트.",
        "category": "C",
        "expected_shape": "rising",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {
            "start_below": 0.50,  # 천천히 시작
            "end_above": 0.70,  # 점점 신나짐 → 끝은 높아야 함
        },
    },
    # Category D: 회귀(stage_count 능동조정)
    "D1": {
        "text": "준비운동-본운동-스트레칭 순서로 러닝 플레이리스트 만들어줘.",
        "category": "D",
        "expected_shape": "peak",
        "target_minutes": None,  # 사용자가 명시하지 않음 (모델이 추정해야 함)
        "peak_minute": None,
        "magnitude_checks": {
            "peak_above": 0.65,  # 러닝 = 본운동 중심이 높음
        },
    },
    # Category E: 극단값 활용(Phase 2, DESIGN.md §9) — 위로형
    "E1": {
        "text": "오늘 너무 힘들었어... 나한테 위로가 되는 플리 짜줘.",
        "category": "E",
        "expected_shape": "rising",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"start_below": 0.15, "end_below": 0.65},
    },
    "E2": {
        "text": "지친 하루 끝에 마음 편해지는 노래로 채워줘. 처음엔 그냥 무너져도 괜찮으니까.",
        "category": "E",
        "expected_shape": "rising",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"start_below": 0.10, "end_below": 0.65},
    },
    # Category F: 극단값 활용(Phase 2, DESIGN.md §9) — 인터벌 스파이크
    "F1": {
        "text": "5km 동안 조깅할 때 들을 플리 짜줘. 중간에 한번 빠르게 뛸때 쯔음 도파민을 터뜨려줘.",
        "category": "F",
        "expected_shape": "peak",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"peak_above": 0.90, "first_below": 0.55, "end_below": 0.55},
    },
    "F2": {
        "text": "헬스장에서 웨이트 하는데 세트 사이사이 짧게 전력질주하듯 강하게 터지는 구간 하나만 넣어줘. 나머진 무난하게 가줘.",
        "category": "F",
        "expected_shape": "peak",
        "target_minutes": None,
        "peak_minute": None,
        "magnitude_checks": {"peak_above": 0.90, "first_below": 0.55, "end_below": 0.55},
    },
}
