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

## 추가 조사 메모 (2026-07-13, 착수만 하고 R&D팀에 이관)

`data/legacy/songs_master_legacy.csv`(661행, 제거 전)와 `data/songs_master.csv`(659행, 제거 후)를
`_quiet_params()`+seed=0으로 각각 재현해 실측치 0.437(제거 후)이 정확히 재현됨을 확인함(우연/버그
아님, 실제 데이터 기반 값).

**유력 가설(미검증)**: `build_setlist`의 Stage A에서 `remaining = {s.idx: s for s in pool}`
(딕셔너리, `pool` 순서 보존) → 매 스테이지 `rng.shuffle(window)` 호출이 **하나의 공유 RNG를
순차 소비**하는 구조(`src/backend/app/domain/selection.py` L191~222). `window`(허용창 내 후보) 길이는
`pool`에서 몇 곡이 빠졌느냐에 따라 스테이지마다 미세하게 달라지므로, `rng.shuffle`이 소비하는 난수
개수도 스테이지마다 바뀐다. 즉 곡 2개 제거가 **뒤따르는 모든 스테이지의 RNG 정렬 전체를 밀어버릴 수
있음** — 이는 "후보 풀이 실제로 나빠졌다"가 아니라 RNG 상태가 어긋나는 구조적 아티팩트일 가능성.

**검증 방법 제안**: 각 스테이지의 `window` 길이·`chosen` 목록을 제거 전/후로 나란히 로그를 찍어
비교. 만약 특정 스테이지에서 `window` 길이가 달라졌고 그 지점부터 이후 모든 pick이 달라진다면
가설 확인. (스테이지별 RNG를 분리하거나 `rng.sample`처럼 소비량이 고정된 방식으로 바꾸면 완화될
수 있음 — 단, 이 경우도 검증 필요.)

## 참고

- PR: https://github.com/sbb2002/bandori-playlist-maker/pull/7
- 관련 코드: `src/scripts/data/build_master.py` (`_CONFIRMED_DUPLICATE_UPLOADS`),
  `src/tests/test_integration.py` (`test_boundary_tension_continuity_is_smooth`)
- R&D 근거 문서: `docs/research/2026-07-11-playlist-sequencing-strategy.md` §4.2
