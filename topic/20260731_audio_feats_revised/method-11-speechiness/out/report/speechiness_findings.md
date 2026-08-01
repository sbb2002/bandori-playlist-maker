# method-11-speechiness 분석 결과

## 두 지표 개요

### 1. speech_median (4Hz 변조 에너지)
- **측정 방법**: Scheirer-Slaney(1997) 알고리즘으로 **보컬 스템**의 4Hz 변조 에너지를 추출
- **의미**: 가사가 포함된 보컬 부분에서 나타나는 음성 변조 비율 (0~1 범위)
- **통계**:
  - 평균: 0.067
  - 표준편차: 0.018
  - 범위: 0.022~0.145

### 2. vad_speech_ratio (VAD 기반 음성 비율)
- **측정 방법**: inaSpeechSegmenter 딥러닝 모델로 **보컬 스템**에서 프레임별 음성/비음성 판정
- **의미**: 음성으로 판정된 프레임 비율의 트랙 평균
- **통계**:
  - 평균: 0.168
  - 표준편차: 0.119
  - 범위: 0~0.637
- **주의**: 초기 `detect_gender=True` 버그로 전 곡이 0.0으로 산출되었다가, 라벨 매칭 로직 수정 후 `detect_gender=False`로 재산출한 값

## 두 지표 관계 분석

### 상관 분석
- **Spearman ρ = 0.204** (p < 0.001)
- **해석**: 통계적으로 유의한 약한 양의 상관
- **원인**: 두 지표는 서로 다른 신호를 측정하기 때문
  - `speech_median`: 4Hz 주기의 변조 에너지 — 음성의 리듬적 특성 포착
  - `vad_speech_ratio`: 딥러닝 기반 음성/비음성 이진 판정 — 음성 구간의 시간 비율
  - 두 메커니즘이 다르므로 완전 일치는 기대하기 어려움

### 분포 특성
- `speech_median`: 상대적으로 좁은 범위(0.022~0.145), 낮은 편차(std=0.018)
  - 보컬 스템 추출 품질이 일정하며, 대부분의 곡이 0.04~0.09 범위
- `vad_speech_ratio`: 훨씬 넓은 범위(0~0.637), 높은 편차(std=0.119)
  - 곡별로 음성 비율 편차가 큼 (간주 vs 가사 비율 차이)

## 밴드별 분석 (표본 10곡 이상)

| 밴드 | N | speech_median 평균 | speech_median 표준편차 | vad_speech_ratio 평균 | vad_speech_ratio 표준편차 |
|------|---|-------------------|----------------------|----------------------|--------------------------|
| poppin_party | 116 | 0.0608 | 0.0167 | 0.1607 | 0.1076 |
| roselia | 91 | 0.0600 | 0.0141 | 0.1517 | 0.0910 |
| raise_a_suilen | 79 | 0.0717 | 0.0204 | 0.1362 | 0.0927 |
| mugendai_mutype | 77 | 0.0781 | 0.0205 | 0.1718 | 0.1304 |
| pastel_palettes | 74 | 0.0684 | 0.0148 | 0.1357 | 0.1208 |
| afterglow | 72 | 0.0707 | 0.0172 | 0.2240 | 0.1406 |
| hello_happy_world | 72 | 0.0783 | 0.0159 | 0.1751 | 0.1244 |
| mygo | 60 | 0.0682 | 0.0143 | 0.2156 | 0.1454 |
| morfonica | 58 | 0.0616 | 0.0121 | 0.1846 | 0.1027 |
| ave_mujica | 29 | 0.0463 | 0.0115 | 0.1320 | 0.0908 |

**주목 사항**:
- **speech_median 범위**: 0.0463(ave_mujica)~0.0783(hello_happy_world) — 밴드별 변조 특성의 차이는 0.032, 전체 데이터 평균의 47% 수준으로 유의미한 편차
- **hello_happy_world & mugendai_mutype**: speech_median이 상대적으로 높음 → 가사 중심적이고 변조 리듬이 강한 성악 스타일
- **ave_mujica & roselia**: speech_median이 상대적으로 낮음 → 간주 비중이 높거나 매끄러운 성악 톤 특성
- **vad_speech_ratio 범위**: 0.1320(ave_mujica)~0.2240(afterglow) — VAD 기반 음성 시간 비율도 밴드별로 큰 차이 (음악 구성 스타일 차이 반영)
- **afterglow & mygo**: vad_speech_ratio가 높음 → 보컬이 많은 곡 구성 또는 적극적인 성악
- **raise_a_suilen & pastel_palettes**: vad_speech_ratio가 낮음 → 상대적으로 간주/인스트루멘탈 비중이 높음

## 코드 검증

✅ **보컬 스템 적용 확인**:
- `extract_speechiness_stem.py`에서 `vocal_path`만 사용하여 풀믹스 적용 오류 방지
- SPEC.md 경고사항(풀믹스 적용 시 4Hz 변조가 템포와 교락) 준수됨

## 결론

두 지표는 음성 특성을 보완적으로 측정하는 도구:
- `speech_median`: 음성의 변조 리듬 (마이크로 수준)
- `vad_speech_ratio`: 음성 구간의 시간적 분포 (매크로 수준)

약한 상관(ρ=0.204)은 결함이 아니라 서로 다른 특성을 포착하고 있음을 의미하며, 향후 분석에서 두 지표를 동시 활용하면 음성 특성을 더욱 정교하게 파악할 수 있음.

### 주의사항
- 보컬 스템은 기존 스템 분리 품질에 의존
- vad_speech_ratio는 inaSpeechSegmenter의 음성/비음성 판정 정확도에 의존
- 재분석 시 `detect_gender=False` 설정 필수

---

## 종합 해석(2026-08-01): 두 지표는 서로 다른 축을 재고 있음 — 폐기하지 않고 활용처 재검토

### 1. speech_median 상/하위 5곡 청취 검증 — "음절 밀도" 신호로 확인됨

| 순위 | 밴드 | 곡명 | speech_median | URL |
|---|---|---|---|---|
| 상위 1 | raise_a_suilen | 神っぽいな (Cover) | 0.1448 | https://youtu.be/J1pFz1b08f8 |
| 상위 2 | mugendai_mutype | みゅーたんとミュータント | 0.1329 | https://youtu.be/qnHJDWgLkvw |
| 상위 3 | raise_a_suilen | Bling-Bang-Bang-Born (Cover) | 0.1327 | https://youtu.be/ciUhdk5mxt4 |
| 상위 4 | mugendai_mutype | フォニイ (Cover) | 0.1320 | https://youtu.be/0makuFTnChs |
| 상위 5 | mugendai_mutype | YoU kNOw the overture | 0.1272 | https://youtu.be/UWHzX6SpizM |
| 하위 1 | mugendai_mutype | 翼をください (Cover) | 0.0218 | https://youtu.be/RGByUSGhQgE |
| 하위 2 | ave_mujica | Ether | 0.0256 | https://youtu.be/z6k7YIIZ6Hk |
| 하위 3 | poppin_party | ミライトレイン | 0.0293 | https://youtu.be/amlyxSdWmTg |
| 하위 4 | mugendai_mutype | 元気を出して (Cover) | 0.0297 | https://youtu.be/RzgsdgCkFjU |
| 하위 5 | poppin_party | SAKURA MEMORIES | 0.0299 | https://youtu.be/lQF_5FOrl7k |

연구자 직접 청취 결과, 상위곡은 음절을 빠르게 쏟아내는(속사포/랩에 가까운) 가사 전달,
하위곡은 한 음을 길게 늘여 부르는 발라드풍 창법으로 확인됨 — speech_median이 밴드/장르가
아니라 **"음절 밀도(가사 전달 속도)"**를 실제로 포착하고 있음을 뒷받침.

### 2. vad_speech_ratio = 0.0인 17곡 — 판정 실패의 원인

전체 736곡 중 17곡이 vad_speech_ratio 정확히 0.0으로 산출됨(`vad_error`는 전부 NaN,
`vad_n_frames`도 15~31개로 정상 — 즉 세그멘테이션 자체는 성공했으나 어떤 세그먼트도
"speech" 라벨을 받지 못함).

- 하위 5곡(모두 0.0): afterglow "READY STEADY GO (Cover)"·"カサブタ", pastel_palettes
  "With〜きみとわたしたちの物語〜"·"ReReReエボリューションず☆"·"ハッピーシンセサイザ (Cover)"
- 이 17곡의 speech_median은 0.022~0.109로 넓게 분포 — "음절이 느려서 0이 됐다"는
  단순 설명은 성립하지 않음.
- **원인 추정**: `inaSpeechSegmenter`는 방송 음성(아나운서/MC) vs 배경음악(BGM)을
  구분하도록 학습된 모델이라, 피치가 뚜렷한 선율적 보컬은 "speech"가 아니라
  "music"으로 통째로 오분류되기 쉬운 구조적 한계가 있음. 노래하는 보컬 전체를
  "music"으로 인식해 speech 구간이 0으로 산출된 것으로 판단됨.

### 3. "단조로운 낭독조 vs 선율적" 가설 검증 — speech_median은 지지, VAD는 기각

가설: "아나운서처럼 단조롭게 말할수록 값이 높고, 빠르든 느리든 선율(피치 변화)이
있을수록 값이 낮을 것이다."

mood_warmth 연구(`topic/20260716_mood_warmth/vocal_features_full.csv`, 80곡 파일럿
표본)의 피치 변동 지표(`f0_range_st`, `f0_std_st`)와 교차 검증한 결과:

| | f0_range_st 상관(r) | f0_std_st 상관(r) |
|---|---|---|
| speech_median | -0.349 | -0.411 |
| vad_speech_ratio | -0.099 | -0.082 |

- **speech_median**: 가설과 방향이 일치하는 중간 수준 상관(r≈-0.35~-0.41). 피치
  변동폭이 좁을수록(단조로울수록) speech_median이 높아지는 경향이 실제로 확인됨.
- **vad_speech_ratio**: 사실상 무상관(r≈-0.08~-0.10). "단조로울수록 VAD가 높다"는
  가설은 이 표본에서 지지되지 않음 — VAD의 speech 판정은 피치 변동폭과 무관한
  다른 요소(스펙트럼 형태·포먼트 구조 등)에 좌우되는 것으로 보임.
- 표본이 80곡(전체 736곡 중 mood_warmth 파일럿용 일부)이라 잠정적 결론이며, 전체
  카탈로그로 f0 변동폭을 확장 계산해 재검증할 필요가 있음.

### 결론 — 폐기하지 않되 활용처는 분리해서 고민

- **speech_median**: "가사 음절 밀도/단조로움" 축을 실제로 반영하는 것으로 검증됨.
  danceability·acousticness와 같은 급의 "좁은 필터 용도"(예: 속사포 가사 곡,
  낭독조 곡 탐지)로 유지.
- **vad_speech_ratio**: 위 가설로는 설명되지 않는 별개의 신호이며, 학습 도메인(방송
  음성 vs BGM) 불일치로 노래 전체가 "music"으로 오분류되는 사례(17곡, 0.0 산출)가
  확인됨. 다만 상위 10곡 중 8곡은 speech_median 71~96퍼센타일과 겹쳐(방향성 자체는
  일부 공유) 완전히 무의미하진 않으므로, 폐기보다는 **정확히 무엇을 재는지 재정의가
  필요한 상태**로 보류.
- liveness·instrumentalness는 각각 관중소음탐지·보컬-악기 믹스밸런스를 재는
  지표라 speechiness(가사 전달 스타일)와는 개념이 달라 대체재가 될 수 없음.
