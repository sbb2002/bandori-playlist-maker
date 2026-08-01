# Danceability 분석 결과

## 데이터셋 개요
- **표본수**: 736곡
- **밴드**: 13개 (표본 10곡 이상: 10개)
- **피처**: `dfa_alpha`, `danceability_norm`, `danceability_clf_prob`, `dfa_alpha_native` (선택)

## 컬럼 설명

### 1. `dfa_alpha` (Essentia 원시값)
- **정의**: Essentia Danceability 알고리즘에서 추출한 Detrended Fluctuation Analysis (DFA) 지수
- **스케일**: 약 0.7~1.1 (원시값, 정규화되지 않음)
- **해석**: **낮을수록 리듬이 규칙적** → danceable
- **성격**: 결정론적, 기계학습 아님 (Proxy X)

### 2. `danceability_norm` (상대 정규화값, 0-1)
- **정의**: 카탈로그 661곡 내 `dfa_alpha` 백분위 기반 정규화
  - 수식: `1 - percentile_rank(dfa_alpha)`
  - α 낮음 → norm 높음 (1에 가까움) → 더 danceable
- **스케일**: 0.0 ~ 1.0
- **용도**: **같은 카탈로그 내 상대적 순위 비교**에 최적

### 3. `danceability_clf_prob` (ML 분류기 확률)
- **정의**: Essentia 사전학습 Danceability 분류기(MusiCNN 임베딩 기반)의 확률값
- **스케일**: 약 0.9 ~ 1.5 (확률이 아닌 점수, 범위 외 가능)
- **성격**: Spotify 정의를 직접 학습한 것이 아니라 별도 라벨셋 기반 → **Proxy, 참고용**
- **주의**: 절대값 해석 불가, 같은 곡 내 상대값 비교만 의미

### 4. `dfa_alpha_native` (네이티브 DFA 참고값)
- **정의**: Essentia 없이 librosa + 통계학으로 구현한 DFA (WSL2 부재 시 참고용)
- **상태**: 대부분 빈 칸 (파일럿 진행 중 미포함)
- **용도**: Essentia 버전과의 상관 검증용(향후)

## 전체 통계 요약

| 지표 | 최솟값 | 최댓값 | 평균 | 표준편차 |
|------|--------|--------|------|----------|
| dfa_alpha | 0.6334 | 1.2027 | 0.9071 | 0.0842 |
| danceability_norm | 0.0000 | 0.9985 | 0.5026 | 0.2891 |
| danceability_clf_prob | 0.8315 | 1.5788 | 1.1121 | 0.1059 |

## `danceability_norm`이 절대값보다 유용한 이유

1. **카탈로그 컨텍스트**: 음악 선곡은 절대값이 아닌 **같은 곡집 내 상대순위**가 중요
   - "이 곡이 정확히 0.65의 danceable인가?"보다 "우리 곡집에서 상위 20% danceable인가?"가 의미 있음

2. **스케일 독립성**: `dfa_alpha`는 곡 특성상 0.7~1.1에 분포
   - 절대값 0.8이 작은 수이지만, 해당 카탈로그에서는 "중상" 수준
   - 정규화하면 직관적인 "0.5 = 카탈로그 평균 수준"

3. **향후 확장성**: 곡이 추가되면 `dfa_alpha`는 불변
   - `danceability_norm`은 재계산 필요하지만, **곡 간 상대순위 의미는 유지됨**

4. **ML 분류기와의 차별화**
   - `danceability_clf_prob`는 외부 모델 기반 (Proxy, 신뢰도 낮음)
   - `danceability_norm`은 **같은 곡집 내 물리적 지표 기반** → 더 일관적

## 밴드별 비교

| 밴드 | n | clf_prob 평균 | clf_prob 표준편차 | norm 평균 | 특징 |
|------|---|---------------|------------------|-----------|------|
| afterglow | 72 | 1.127 | 0.098 | 0.542 | 중상 danceable |
| ave_mujica | 29 | 0.949 | 0.074 | 0.100 | 낮은 danceable |
| hello_happy_world | 72 | 1.196 | 0.097 | 0.740 | 높은 danceable |
| morfonica | 58 | 1.078 | 0.083 | 0.405 | 중 danceable |
| mugendai_mutype | 77 | 1.146 | 0.128 | 0.549 | 중상 danceable |
| mygo | 60 | 1.116 | 0.113 | 0.488 | 중 danceable |
| pastel_palettes | 74 | 1.149 | 0.097 | 0.625 | 중상 danceable |
| poppin_party | 116 | 1.108 | 0.085 | 0.505 | 중상 danceable |
| raise_a_suilen | 79 | 1.095 | 0.084 | 0.468 | 중 danceable |
| roselia | 91 | 1.066 | 0.073 | 0.369 | 중 danceable |


## 주요 발견

1. **분류기 확률의 범위 문제**: `danceability_clf_prob`가 1.0을 초과(최대 1.5+)
   - 확률값이 아니라 점수 → 해석 주의 필요
   - 카탈로그 간 비교 불가

2. **DFA 지수의 효율성**: `dfa_alpha` 정규화가 명확한 상대순위 제공
   - 최상 danceable (norm ≈ 0.98): "Reach Out To The Truth" (afterglow) - α 0.7167
   - 최하 danceable (norm ≈ 0.02): "독創収差" (afterglow) - α 1.0924

3. **밴드별 편차**: 일부 밴드는 높은 danceable 평균, 다른 밴드는 낮은 분포
   - 선곡 성향이나 장르 특성 반영 가능성 있음

## 권장사항

- **향후 분석**: `danceability_norm` 기준으로 밴드별/모드별 선곡 경향 비교
- **ML 모델**: `danceability_clf_prob`는 참고용으로만 사용, 주요 판단 기준 제외
- **검증**: WSL2 구축 후 Essentia 버전 확정 시 네이티브 DFA와 상관도 검증

---

## 종합 분석: 단독 판별력은 약하지만 보조축으로서는 유의미

산출물: `out/fig/band_profile_radar.png` (arousal x valence x danceability_norm x lra
4축 밴드별 레이더, 밴드 중앙값 min-max 정규화)

### 다른 지표와의 상관관계 (n=736)

| 대상 | 상관계수 |
|---|---|
| valence_median | 0.449 |
| lra | -0.440 |
| arousal_median | 0.227 |
| bpm_madmom | -0.036 |
| lufs_integrated | -0.071 |

**템포와는 거의 무관(r=-0.04)** — "빠르면 danceable"이라는 통념과 달리 이 지표는
속도가 아니라 순수 리듬 규칙성만 반영. **lra와는 뚜렷한 음의 상관(-0.44)** —
규칙적인 그루브를 유지하는 곡일수록 곡 전체의 강약 변동폭(lra)이 작은 경향.

### danceability 단독의 한계

밴드 간 중앙값의 표준편차(0.21)가 밴드 내부 표준편차(0.22~0.30)보다 작거나
비슷한 수준 — 밴드 라벨보다 곡 개별 편차가 신호를 삼키는 수준이라, 이 지표
단독으로는 밴드 판별력이 약함.

### lra와 묶었을 때: arousal·valence로 안 갈리던 밴드가 갈림

arousal·valence 좌표가 비슷했던 raise_a_suilen과 roselia를 danceability+lra로
다시 보면:

| 밴드 | danceability_norm | lra |
|---|---|---|
| raise_a_suilen | 0.427 (중앙값) | 4.15 (평균) |
| roselia | 0.307 (중앙값) | 4.72 (평균) |

RAS는 "규칙적 그루브(danceability 높음) + 작은 다이내믹 기복(lra 낮음)" = 클럽
같은 일정한 비트감, roselia는 "덜 규칙적인 리듬(danceability 낮음) + 큰 다이내믹
기복(lra 높음)" = 몰아치고 웅장한 전개 — 청감상 인상 차이(RAS: 가볍다/신난다/
클럽 같다 vs roselia: 격렬하다/몰아친다/웅장하다)와 정확히 부합.

### 밴드별 4축 프로필 요약 (정규화값, 괄호는 원값)

| 밴드 | arousal | valence | danceability | lra |
|---|---|---|---|---|
| hello_happy_world | 0.58 (6.86) | 1.00 (6.26) | 1.00 (0.805) | 0.00 (2.88) |
| pastel_palettes | 0.48 (6.80) | 0.96 (6.20) | 0.80 (0.652) | 0.16 (3.33) |
| mugendai_mutype | 0.01 (6.54) | 0.57 (5.61) | 0.69 (0.569) | 0.57 (4.53) |
| afterglow | 1.00 (7.09) | 0.80 (5.96) | 0.64 (0.541) | 0.04 (2.98) |
| poppin_party | 0.61 (6.87) | 0.82 (6.01) | 0.60 (0.500) | 0.05 (3.02) |
| mygo | 0.63 (6.89) | 0.39 (5.42) | 0.57 (0.481) | 0.07 (3.08) |
| raise_a_suilen | 0.46 (6.79) | 0.27 (5.24) | 0.50 (0.427) | 0.20 (3.45) |
| morfonica | 0.16 (6.63) | 0.55 (5.64) | 0.40 (0.353) | 0.29 (3.73) |
| roselia | 0.29 (6.70) | 0.49 (5.55) | 0.34 (0.307) | 0.52 (4.38) |
| ave_mujica | 0.00 (6.46) | 0.00 (4.87) | 0.00 (0.049) | 1.00 (5.78) |

- 대부분 밴드(hello_happy_world, pastel_palettes, afterglow, poppin_party, mygo)는
  큰 삼각형(고arousal·고valence·고danceability, 저lra) 모양으로 수렴 —
  대다수 곡이 리듬 변칙 없이 정형화된 팝/록 그루브를 따른다는 뜻.
- **예외 5개 밴드(mugendai_mutype, raise_a_suilen, morfonica, roselia,
  ave_mujica)만 다른 모양**:
  - mugendai_mutype: arousal 최하위권이면서도 valence는 평균 근처, danceability도
    상위권인데 lra도 높은 편 — "낮은 각성, 밝음 유지, 규칙적이나 기복도 있음".
  - raise_a_suilen: valence 낮고 danceability 중상, lra 낮음 — 규칙적 그루브 +
    작은 기복 + (원값 기준) 상위권 arousal.
  - morfonica: RAS와 비슷한 궤적이나 valence가 뚜렷이 더 높음.
  - roselia: 이 5개 밴드 중 danceability 최저·lra 최고 — 변칙성이 가장 큼.
  - ave_mujica: 4축 모두 극단(arousal/valence/danceability 최저, lra 최고) —
    아래 검증 참고.

### ave_mujica 극단값 검증(버그 아님, 진짜 신호로 판단)

- `dfa_alpha`를 곡별로 확인한 결과, 736곡 전체 카탈로그의 **최댓값(가장 불규칙,
  1.2027)이 ave_mujica의 곡("神さま、バカ")**이며, 29곡 대부분이 전체 분포 상위
  25%(0.957 이상)를 초과함.
- error 컬럼 공백(정상 추출), duration 180~320초(정상 범위) — 파이프라인 결함
  흔적 없음.
- **완전히 독립적인 별도 모델(`danceability_clf_prob`, ML 분류기)도 같은 방향**:
  전체 평균 1.11인데 ave_mujica는 대부분 0.85~0.99로 낮은 쪽에 몰림 — 서로 다른
  두 방법(신호처리 DFA vs ML 분류기)이 같은 결론을 내려 우연으로 보기 어려움.
- 서사적으로도 "Symbol I~IV", "Choir 'S' Choir" 등 프로그레시브/극적 구성(템포
  변화, 프리폼 전개)이 많아 정박 그루브가 약한 것이 납득됨. → **데이터 유효**.
- **millsage(n=2)**: 표본 부족으로 밴드 결론 불가하나, 참고로 한 곡(dfa=0.910,
  중앙값 근처)과 한 곡(dfa=1.056, 상위 30% 불규칙)으로 나뉨 — 다른 모든
  밴드별 비교에서도 n<10이라 제외되어 온 밴드.

### 결론

danceability_norm은 **단독으로는 판별력이 약하고(밴드 간 편차가 밴드 내부 편차에
묻힘) 다른 지표(템포·러프니스)와의 상관도 거의 없지만, lra와 묶었을 때 arousal·
valence만으로는 구분되지 않는 소수 밴드(mugendai_mutype·raise_a_suilen·
morfonica·roselia·ave_mujica)의 "리듬 변칙성" 성격을 갈라내는 보조축으로는
유의미**하다. 주 선곡 기준으로 쓰기엔 근거가 약하지만, 폐기하지 않고 lra와 짝지어
보조 피처로 유지할 가치가 있음.

---
*분석일: 2026-08-01*
*데이터셋: 736곡*
