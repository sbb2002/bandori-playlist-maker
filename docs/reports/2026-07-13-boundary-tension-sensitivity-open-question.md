# 2026-07-13 — boundary_tension 회귀가드 민감도, 미조사 오픈 이슈

## 배경

PR #7(`fix/dedupe-duplicate-video-uploads`, main에 머지됨)에서 `data/songs_master.csv`의
중복 업로드 2곡을 제거했다:

- idx 525 (raise_a_suilen · R・I・O・T, idx 501의 중복 업로드)
- idx 588 (roselia · Neo-Aspect, idx 570의 중복 업로드)

두 쌍 모두 사용자가 직접 청취해 완전히 동일한 곡임을 확인했고, key·camelot·tempo_excerpt가
소수점까지 일치해 교차검증됨. 원래 `build_master.py`에는 이 2쌍이 "별개 레코딩"이라 band+song
조인이 금지된다고 기록돼 있었으나, 이는 잘못된 가정이었음이 밝혀져 정정함(자세한 내용은
PR #7 및 `src/scripts/data/build_master.py`의 `_CONFIRMED_DUPLICATE_UPLOADS` 참고).

## 발견한 이상 현상 (미해결)

660행 → 658행(마스터 기준 661→659, 헤더 포함)으로 **곡을 딱 2개만 제거**했는데,
`src/tests/test_integration.py::test_boundary_tension_continuity_is_smooth`의 seed=0
고정 시나리오(조용한 요청, `_quiet_params()`) 실측값이 크게 움직였다:

- 제거 전: 평균 gap < 0.40 (통과)
- 제거 후: 평균 gap = 0.437 (실패 → 임계값을 0.44로 재조정, PR #7에서 사용자 승인)

베이스라인(연속성 로직 미적용) 값은 ~0.56이므로 0.437도 여전히 개선된 수준이긴 하지만,
**후보 풀에서 곡 2개(전체의 0.3%)가 빠졌다고 이 정도로 값이 튀는 것은 이상하다.**
가능한 원인:

1. **우연**: 빠진 두 곡(idx 525, 588) 중 하나가 seed=0 시나리오에서 마침 인접 전환이
   유난히 매끄러운 "다리" 역할을 하던 곡이었고, 대체된 곡의 outro/intro 조합이
   상대적으로 나빴을 뿐일 수 있음.
2. **알고리즘 취약점**: `build_setlist`(선곡 엔진, `src/backend/app/domain/selection.py`
   추정 — 미확인)가 소수 후보 변화에 과민하게 반응하는 구조적 문제일 수 있음. 예를 들어
   특정 에너지/카멜롯 구간에 후보가 원래도 적어서, 하나만 빠져도 대체 후보 풀이 확
   나빠지는 경우.

## 다음에 조사할 것

- `build_setlist(songs, _quiet_params(), target_seconds=3600, rng=random.Random(0))`를
  제거 전/후 데이터로 각각 재현해서 실제로 어떤 idx들이 선곡되는지 비교.
- 곡 2개 제거 전후로 어느 지점의 pick이 바뀌었는지(바뀐 pick의 outro/intro energy 확인).
- 만약 알고리즘이 소수 후보 변화에 민감하다면, `stage_count`나 카멜롯 인접 후보 풀 크기가
  특정 구간에서 지나치게 좁은 건 아닌지 `src/backend/app/domain/selection.py`,
  `src/scripts/data/camelot.py` 쪽을 확인.

## 참고

- PR: https://github.com/sbb2002/bandori-playlist-maker/pull/7
- 관련 코드: `src/scripts/data/build_master.py` (`_CONFIRMED_DUPLICATE_UPLOADS`),
  `src/tests/test_integration.py` (`test_boundary_tension_continuity_is_smooth`)
- R&D 근거 문서: `docs/research/2026-07-11-playlist-sequencing-strategy.md` §4.2

## 후속 조사 결론 (2026-07-14, REFUTED — 대안 원인 규명)

`docs/research/2026-07-14-boundary-tension-rng-sensitivity-verified.md`에서 RNG-정렬 가설을
직접 재현·검증했다. **결론: "RNG 소비량이 스테이지 간 어긋난다"는 가설은 반증됨** — Stage A
`rng.shuffle(window)`의 window 크기는 제거 전/후 세 스테이지 모두 완전히 동일했다(44/38/32).

실제 원인은 `Song.energy`(강도)가 `song_repo._percentile_ranker()`로 **후보 풀 전체 분포에
대한 상대적 percentile rank**로 계산된다는 점이다. 곡을 2개만 제거해도 나머지 모든 곡의
percentile이 미세하게 재계산되고, 이 미세한 변화가 Stage A 정렬 키(`abs(energy-target)`)의
동점 근방 순서를 뒤집어 `rng.shuffle`에 들어가는 리스트 순서 자체가 달라진다 — 같은 seed,
같은 window 크기라도 입력 순서가 다르면 셔플 결과가 달라지는 것이 분기의 직접 원인이었다.
가설 ①(우연)도 함께 반증됨: 제거된 idx 525/588은 애초에 이 시나리오의 선곡 후보에도 없었다.

`python -m pytest` 9개 테스트 전부 통과, 현재 임계값 0.44는 유효(실측 0.4374, 여유 ≈0.0026).
권장 후속 조치(별도 `feature/*` 브랜치 몫): 스테이지별 독립 RNG 시드 분리, 회귀가드를 절대
임계값 대신 상대적 개선폭 기준으로 전환, energy percentile 재계산 민감도 완화 검토.
