# energy / energy_full 특성 검증 — tempo·brightness·원시 오디오 피처와의 관계, 밴드별 장르 편향

> 실행 스크립트: `src/method-1/`(4개 파이썬 스크립트). 2.2~2.5의 원시 서브피처·GT·백분위
> 분석은 대화 세션 중 1회성으로 수행했고 별도 스크립트 파일로 남기지 않았다(재현 절차는 각
> 하위 절의 "실험 방법"에 그대로 기술).

## 1. 배경

`groq_multistage_adapter`(2회차 스킵 기능, `feature/multistage-previous-params-skip`)에
brightness 산출을 추가하는 작업을 검증하던 중, 프로덕션 `energy`(발췌구간 기반)가 tempo와
관계가 있는지 확인하는 데서 조사가 시작됐다. tempo와는 무관하다는 게 확인된 뒤, brightness와도
무관함이 드러났고, 이어서 `energy`와 `energy_full`(전곡 재추출 보정치, 아직 프로덕션 미채택
컬럼)을 비교하자 오히려 음의 상관(r≈-0.45)이 나와 `energy_full`이 실제로 무엇을 포착하는지
검증하게 됐다.

이 과정에서 사용자가 두 가지를 직접 의심했다:
1. brightness(= mode_score 정규화값)가 그래프상 중심에 고르게 몰려 보이는 게 정규화 절차
   자체의 인공물이 아닌지.
2. `energy_full`이 산출값(합성 지표)인데, 헤비메탈/고딕 이미지의 **ave_mujica** 밴드가 오히려
   `energy_full` 분포에서 낮게 나오는 게 뭔가를 놓치고 있는 신호가 아닌지.

**사용자 명시: 이 편향 문제가 해결되지 않으면 `energy_full`을 실사용하는 후속 feature 작업은
머지할 수 없다.** (2026-07-30 대화 세션에서 명시)

## 2. 방법

### 2.1 `energy`(프로덕션) vs tempo·brightness·전곡 강도지표(i_*)

**용어 정리**
- `energy`: 선곡 엔진(`domain/selection.py`)이 실제로 소비하는 발췌구간 기반 강도(0~1).
- `tempo_excerpt`/`bpm`: 발췌구간 기준 추정 BPM.
- `mode_score`: brightness 산출 원료(`_brightness_scores()`가 이 값을 min-max 정규화).
- `i_mean`/`i_std`/`i_max`/`i_min`/`i_start`/`i_end`: 전곡 프레임별 강도 포락선 통계
  (`Song.intro_energy`/`outro_energy`와 동일 스케일).

**실험 방법**
1. `songs_master.csv`에서 `eligible_band=True` ∧ `energy` 존재 701곡을 추출한다.
2. `energy`와 각 피처 간 Pearson r을 계산한다.
3. `energy` 하위 25%(175곡)·상위 25%(175곡) 평균을 비교한다.

**평가 방법**: |r|<0.1은 사실상 무관, 0.1~0.3 약함, 0.3~0.5 중간, 그 이상 강함으로 본다
(경험적 구간 구분, 통계적 유의성 검정은 별도로 하지 않았다).

### 2.2 `energy_full` — 원시 오디오 서브피처와의 관계

**용어 정리**: `data/full_audio_features.csv`의 전곡 스펙트럼/타악 서브피처
(`zcr_mean`=거칠기, `perc_mean`=HPSS 타악 에너지 비율, `onset_mean`=어택/타격 밀도,
`cen_mean`=스펙트럼 중심(음색 밝기), `contrast_mean`=스펙트럼 대비, `rms_mean`=평균 음압).

**실험 방법**
1. `songs_master.csv`(idx 기준)와 `full_audio_features.csv`를 조인(730곡).
2. `energy_full`과 각 서브피처 간 Pearson r을 계산한다.

**평가 방법**: 2.1과 동일 기준.

### 2.3 GT 라벨 기반 `energy_full` 실사용 검증

**용어 정리**: `src/scripts/data/build_energy_full.py`(main 브랜치)에 하드코딩된
ground-truth 라벨 3종 — GT_QUIET(14곡, 조용해야 정상), GT_LOUD(14곡, 시끄러워야 정상),
GT_MISJUDGED(8곡, "조용한 인트로에 속아 오판된 실제 시끄러운 곡" — energy_full이 반드시
끌어올려야 하는 핵심 대상, 그중 ★4곡=STRICT4).

**실험 방법**
1. eligible ∧ energy_full 존재 730곡을 energy_full 오름차순 정렬해 순위(1~730)를 매긴다.
2. GT_QUIET/GT_LOUD/GT_MISJUDGED 각 idx의 실제 순위를 조회한다.

**평가 방법**: GT_QUIET는 순위가 낮아야, GT_LOUD/GT_MISJUDGED는 순위가 높아야 "정상"으로
판정한다. GT_MISJUDGED는 이 컬럼이 존재하는 이유 그 자체이므로 가장 엄격하게 본다(특히
STRICT4).

### 2.4 `mode_score` 원본 분포 — 정규화 인공물 여부 확인

**실험 방법**: `_brightness_scores()`가 적용되기 **이전**의 `mode_score` 원본값(730개)의
min/max/mean/median/std와 10구간 히스토그램을 직접 계산한다.

**평가 방법**: min-max 정규화(`_brightness_scores()`가 쓰는 방식)는 선형 재척도라 분포
**모양 자체**는 바꾸지 않는다. 따라서 원본이 이미 종형(가운데가 볼록)이면 brightness가
중심에 몰려 보이는 건 정규화 인공물이 아니라 원본 피처의 실제 성질로 판정한다.

### 2.5 밴드별 `energy_full` 분포 + ave_mujica 이상치 원인 추적

**용어 정리**: `build_energy_full.py`의 실제 최종 합성식(코드 확인, 부장 확정 2026-07-11) —

```
FINAL_FEATS = [perc_mean, onset_mean, zcr_mean, cen_mean, flat_mean, rms_p90]
FINAL_W     = [    1,         1,        1,       1,        1,          2   ]

# 1) 피처별 robust z-score(eligible 풀 기준, 중앙값·MAD)
z = (value - median) / (MAD × 1.4826)

# 2) 방향(orientation) 자동 결정: GT_LOUD 평균 z ≥ GT_QUIET 평균 z 이면 +1, 아니면 -1
# 3) 가중 합성
composite = Σ(w_i × orientation_i × z_i) / Σw_i

# 4) energy_full = eligible 풀 안에서 composite의 백분위 순위(0~1)
```
`rms_p90`(피크 라우드니스)만 가중치 2배 — 코드 주석: "FIRE BIRD(다이나믹 빌드업 곡) 오판을
구제하려고 부장이 나중에 추가."

**실험 방법**
1. 밴드별 `energy_full` 평균/표준편차를 계산해 정렬한다.
2. 위 산출 공식을 그대로 재구현해(같은 GT_QUIET/GT_LOUD idx, 같은 z-score·orientation·가중치
   식) 6개 피처 각각의 `orientation` 부호와, ave_mujica(n=29) 각 피처의 oriented z-score
   평균을 직접 계산한다.

**평가 방법**: 각 피처의 orientation이 상식(예: rms_p90↑=더 시끄러움)과 일치하는지 확인하고,
ave_mujica의 낮은 energy_full이 (a) 해당 피처들의 실제 낮은 값 때문인지, (b) 방향 결정
로직 자체의 부작용 때문인지를 가중 기여도(`weight × oriented_z`)로 분해해 구분한다.

## 3. 결과

### 3.1 `energy`(프로덕션)는 tempo·brightness와 거의 무관

| 대상 | r |
|---|---|
| tempo_excerpt | -0.059 |
| bpm | -0.050 |
| mode_score(brightness 원료) | -0.057 |
| i_min | +0.349 |
| i_std | -0.374 |
| i_max | -0.101 |

하위 25% vs 상위 25% 비교에서도 tempo(-3.4분 차이, 사실상 무의미)·mode_score(0.042→0.014,
무의미) 모두 차이가 없었다. 반면 `i_min`(가장 조용한 순간의 강도)은 하위 -1.32→상위 -0.88로
뚜렷이 올라가고 `i_std`(변동폭)는 0.97→0.82로 내려가, **"energy가 높다" = "가장 조용한 순간이
없다(다이나믹 레인지가 좁다)"**에 가깝다. → `fig/heatmap_overall.png`, `fig/heatmap_by_band.png`,
`fig/energy_vs_tempo.png`.

### 3.2 `energy_full`은 원시 서브피처와 강하고 해석 가능하게 상관됨

| 서브피처 | r |
|---|---|
| zcr_mean/p90 | +0.69 / **+0.76** |
| flat(스펙트럼 평탄도) | +0.67 / +0.71 |
| cen(음색 밝기) | +0.65 / +0.68 |
| perc(타악 비중) | +0.60 |
| onset(어택 밀도) | +0.47 |
| contrast | -0.27 |
| acousticness_proxy | **-0.65** |
| **rms_mean/p90** | **-0.52 / -0.54**(★build_energy_full.py 자체가 "라우드니스 정규화 때문에 무용"이라 명시) |

방향성 자체는 "거칠고 타악·어택 많고 음색 밝고 어쿠스틱하지 않을수록 energy_full 높음"으로
잘 잡혀 있다. → `fig/heatmap_energyfull_brightness.png`, `fig/heatmap_energyfull_brightness_byband.png`.

### 3.3 GT_MISJUDGED 핵심 검증 — 절반 실패, 특히 처救生 완전 실패

| 그룹 | 결과 |
|---|---|
| GT_QUIET(14곡) | 대체로 통과(대부분 순위 400 이내) |
| GT_LOUD(14곡) | 대체로 통과(대부분 순위 400 이상, 예외 1곡) |
| GT_MISJUDGED(8곡, STRICT4=★4곡) | **절반 실패** |

STRICT4 중 ドラマチック！アライブ(rank 616/730)·はいよろこんで(rank 628/730)는 성공, 灼熱
Bonfire!(rank 254/730)·**処救生(rank 1/730, 전체 최하위)**는 실패. 처救生은 이 컬럼을 만든
이유 그 자체인 곡인데 정반대로 나왔다.

### 3.4 `mode_score` 원본부터 이미 종형분포 — 정규화 인공물 아님

원본(정규화 전) `mode_score`: `min=-0.374, max=0.430, mean=0.028, std=0.168`. 10구간
히스토그램(최소→최대): `[12, 35, 95, 113, 123, 110, 93, 76, 56, 17]` — 가운데(4~6번째 구간)가
뚜렷하게 볼록하다. `_brightness_scores()`의 min-max 정규화는 선형 재척도이므로 이 모양을
바꾸지 않는다 → **brightness가 중심에 몰려 보이는 건 원본 피처의 실제 성질이며 정규화
인공물이 아니다.**

### 3.5 ave_mujica — 낮은 energy_full의 진짜 원인은 "rms_p90 방향 반전" 버그

밴드별 energy_full 평균(발췌):

| 밴드 | n | energy_full 평균 |
|---|---|---|
| ave_mujica | 29 | **0.194** |
| roselia | 91 | 0.443 |
| raise_a_suilen | 80 | **0.596** |
| mugendai_mutype | 69 | 0.729 |

같은 "하드한 이미지" 밴드인 raise_a_suilen은 정상적으로 높은데 ave_mujica만 유독 낮다.

**공식을 그대로 재구현해 6개 피처의 orientation을 직접 계산하면:**

| 피처 | orientation | 근거 |
|---|---|---|
| perc_mean | **+1** | GT_LOUD 평균 z ≥ GT_QUIET 평균 z (상식과 일치) |
| onset_mean | **+1** | 〃 |
| zcr_mean | **+1** | 〃 |
| cen_mean | **+1** | 〃 |
| flat_mean | **+1** | 〃 |
| **rms_p90** | **-1** | GT_LOUD 14곡의 raw rms_p90 z-score 평균이 GT_QUIET 14곡보다 **낮게** 나와 방향이 반전됨(라우드니스 정규화 때문 — `extract_full_energy.py`가 이미 "rms 절대값은 무용"이라 경고한 바로 그 문제) |

즉 `rms_p90`은 배제된 게 아니라 **가중치 2배(6피처 중 최대)로 포함돼 있는데, 소규모
GT셋(각 14곡)에서 우연히 방향이 거꾸로 학습됐다.**

ave_mujica(n=29) 각 피처의 oriented z-score 평균(양수=시끄러운 방향으로 기여):

| 피처 | oriented z 평균 | 가중치 | 기여도(가중×z) |
|---|---|---|---|
| perc_mean | -0.767 | 1 | -0.767 |
| onset_mean | -0.687 | 1 | -0.687 |
| zcr_mean | -0.773 | 1 | -0.773 |
| cen_mean | **-1.073** | 1 | -1.073 |
| flat_mean | +0.082 | 1 | +0.082 |
| **rms_p90** | **-1.015** | **2** | **-2.030** |
| **합계 / Σw** | | 7 | **-5.248 / 7 ≈ -0.750** |

`rms_p90`의 raw(방향 반전 전) z-score는 **양수**다(ave_mujica는 실제로 피크 음압이 큼 —
`rms_mean` 기준 전체 730곡 중 81%ile). 그런데 orientation이 -1로 뒤집혀 있어서 이 항목
하나가 **-2.03**을 기여하며, 이는 전체 가중합(-5.248)의 **약 39%**로 6개 피처 중 가장 큰
단일 기여도다. 나머지 5개(perc/onset/zcr/cen/flat)는 방향은 정상이지만 ave_mujica가 원래
그 값 자체가 낮아서(심포닉/고딕 계열답게 거칠기·타악비중·어택밀도·음색밝기가 낮음) 추가로
음의 방향에 기여한다.

**결론적으로 ave_mujica의 낮은 energy_full은 두 가지가 겹친 결과다**: (a) 실제로 거칠기·
타악·어택·음색밝기가 낮은 장르적 특성(방향은 정상, 값 자체가 낮음) + (b) 가장 큰 가중치를
가진 `rms_p90`이 소규모 GT셋에서 우연히 방향이 반전돼, ave_mujica의 진짜 강점(높은 피크
음압)이 오히려 "조용함"의 증거로 잘못 쓰이는 것(b가 전체 음의 기여의 약 39%를 차지 — 단순
장르 편향보다 이쪽이 더 큰 비중).

## 4. 결론

- **`energy`(프로덕션)**: tempo·brightness와 무관, "다이나믹 레인지가 좁다(=시종일관 고르게
  강렬하다)"는 것과 관련. 별도 조치 불필요(기존 동작 그대로 이해하면 됨).
- **`mode_score`/brightness의 중심 집중 분포**: 정규화 인공물 아님, 원본 피처의 실제 성질로
  확인됨. 추가 조치 불필요.
- **`energy_full`은 현재 형태로 프로덕션 채택 불가.** 근거 둘:
  1. GT_MISJUDGED(핵심 검증 대상) 절반 실패, 그중 処救生은 완전 실패(전체 최하위).
  2. **`rms_p90`(가중치 2배, 최대) 방향 반전 버그**: 소규모 GT셋(14/14곡)에서 우연히
     orientation이 -1로 학습돼, 실제로 피크 음압이 큰 ave_mujica가 "조용함"으로 오분류됨.
     전체 음의 기여도의 약 39%를 이 항목 하나가 차지 — 단순 장르 편향이 아니라 자동
     orientation 로직의 구조적 결함.
- **수정 방향**: `rms_p90` orientation을 자동 결정 대신 고정(+1)하거나, GT셋을 늘려 재학습.
  **사용자 결정: 해소 전까지 `energy_full` 사용 feature는 머지 보류.**

## 5. 레퍼런스
- `src/scripts/data/extract_full_energy.py`, `src/scripts/data/build_energy_full.py`(main
  브랜치) — energy_full 산출 파이프라인 원본, GT 라벨 정의.
- `domain/selection.py`의 `_brightness_scores()`(main 브랜치) — brightness 산출 로직.
- 근거 대화: 2026-07-30 세션(`feature/multistage-previous-params-skip` 검증 중 파생).
- 관련 R&D 문서: `document-archive` 브랜치
  `archive/last-papers/research/2026-07-11-playlist-sequencing-strategy.md` §5(전곡 재추출
  권고 원본 근거).
