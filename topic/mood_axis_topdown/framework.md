# 탑다운 검증 프레임워크 — 방법론 설계

> 상태: 설계만 완료, 실행 미착수. `README.md`의 배경·목적을 전제로 한다.

## 0. 핵심 원칙

지금까지 실패한 시도(mode_score를 밝기로 재활용, 가사+음향 late-fusion, 보컬 발성 valence
대리축)의 공통점은 **신호를 먼저 만들고 나중에 검증**하는 순서였다. 이 프레임워크는 순서를
뒤집는다:

1. 어떤 감성 언어를 지원할지 먼저 정한다(목표 어휘).
2. 그 언어에 대한 사람 라벨(ground truth)을 먼저 확보한다.
3. 이미 계산된 모든 후보 신호를 그 라벨과 저비용으로 전수 대조한다.
4. **통과한 신호만** 파이프라인에 연결하고, 그 다음에야 실사용 블라인드 A/B로 넘어간다.

새 피쳐를 개발하는 것은 3단계에서 아무 신호도 통과하지 못한 축에 대해서만, 그것도 마지막
수단으로 고려한다 — "일단 만들어보고 나중에 검증"은 이 프레임워크에서 금지된 순서다.

## 1. 목표 어휘 확정

### 1a. 용어 정리
- **축(axis)**: 사용자 감성 언어 한 그룹이 가리키는 단일 차원(예: intensity, valence).
  서로 다른 표현(신난다/텐션높다/시끄럽다)이 같은 축을 가리킬 수 있다.
- **원재료 쿼리셋**: 이미 존재하는, 실제 사용자 표현을 흉내낸 쿼리 모음. 새로 만들지 않고
  재사용한다.
  - `selection_pipeline/DESIGN_v3.md` §5.1의 R01~R24(24개, 밴드지정/강도·밝기/상황·기능성/
    진행형 아크 4카테고리)
  - `vector_embedding/report/01`, `report/04`의 T1~T3 쿼리(행복한/슬픈/꿀꿀해/신나는/위로/
    자장가)
  - `data/ground_truth_labels.csv`의 `dimension` 컬럼(intensity/brightness/party) — 이미
    "축"으로 확정된 3개

### 1b. 실험 방법
1. 위 원재료 쿼리·라벨 축을 전부 한 목록으로 모은다(중복 표현은 하나로 합침).
2. 사람이 읽고 의미상 군집으로 묶는다(정성 분류, 통계기법 아님 — 쿼리 수가 적어 클러스터링
   알고리즘을 쓸 만큼 크지 않다).
3. 각 군집에 축 이름을 붙인다. 최소 후보(선행 연구가 이미 시사): `intensity`(강도),
   `valence`(밝음↔어두움/기쁨↔슬픔), `pathos`(애절함 — `mood_warmth`가 이미 valence와
   구분해서 다룸), `arousal_vs_calm`(상황/기능성 쿼리가 시사하는 활동성).
4. **규칙**: 새 축을 추가하려면 그 축을 가리키는 실제 쿼리 예시가 최소 2개 이상 있어야 한다.
   예시가 없는 축(이론적으로 있을 법하지만 아무도 그렇게 말 안 하는 축)은 만들지 않는다.

### 1c. 평가 방법
군집화 결과를 사용자에게 제시해 축 목록을 확정받는다(정성 확인, 별도 채점 기준 없음) — 이
단계의 산출물은 "몇 개의 독립 축과 각 축의 대표 쿼리 목록"이라는 합의된 표 하나다.

### 1d. 확정 결과 (2026-07-22, 사용자 확인 완료)

R01~R24(`selection_pipeline/DESIGN_v3.md`), T1~T3(`vector_embedding/report/01·04`),
`ground_truth_labels.csv`의 `dimension` 3종을 취합·군집화한 결과:

| 축 | 대표 쿼리 | ground truth 현황 | 신호 현황 |
|---|---|---|---|
| **intensity** | R02/R03/R07/R08/R10~12, gt `intensity`(36행) | 충분 | 검증됨(`energy_full`) |
| **valence**(밝음↔어두움/기쁨↔슬픔) | R01/R05/R06/R09/R10, T1-Q1/Q2, T2-Q1, gt `brightness`(16행) | 부족(16행, 축소 재정의 필요) | **공백**(전부 실패) |
| **pathos**(애절하나 위로됨 vs 안 됨) | T3-Q1 "위로", `mood_warmth` 원 동기 | **없음**(기존 29행 라벨은 "esora 유사도" 오염 대리 라벨) | **공백**(보컬발성 시도 종결) |
| tempo | 암묵적(R15/R23) | — | 이미 검증됨(`final_bpm`), 재검증 불필요 |

**상황/기능성(R13~R18)·진행형 아크(R19~R24)는 별도 축이 아니라 위 축들의 조합·시간적
궤적으로 처리한다(사용자 확정)** — 새 ground truth 라벨링이나 신호 스크리닝 대상이 아니고,
"상황 어휘 → 기존 축 목표값 매핑"은 이미 3~4단계 LLM 제어가 하는 일(구간분할+감정키워드
→ 에너지)로 흡수된다. 단, party(gt 13행)처럼 intensity로 완전히 설명 안 될 가능성이 있는
하위 라벨은 §2에서 재검토 대상으로 남겨둔다(2c 참조).

**§2(ground truth 확장) 실질 대상은 `valence`·`pathos` 2개 축**으로 좁혀졌다 — intensity는
이미 충분하고 tempo는 축 검증 자체가 불필요하기 때문이다.

## 2. Ground truth 확장

### 2a. 용어 정리
- **기존 자산**: `data/ground_truth_labels.csv`(65행, `idx,band,song,dimension,label` 포맷,
  intensity 36행/brightness 16행/party 13행, 라벨러 인원 미확인).
- **공백(§1d 확정)**: `valence`(밝음↔어두움을 mode_score가 아니라 "사람이 느끼는 감정가"로
  직접 라벨링한 것, 기존 brightness 16행은 부족·재정의 필요)와 `pathos`(현재 라벨 없음 —
  `mood_warmth`의 29곡 "esora 유사도" 라벨은 밝기·강도가 혼재된 대리 라벨이라 부적합, README
  §2단계 해석 참조)가 실질 확장 대상이다. intensity는 36행으로 충분, tempo는 축 검증 자체가
  불필요(§1d).
- **`party` 확인 완료(2026-07-22, 청취 불필요·데이터 대조만)**: `party` 13행 중 11행이
  `intensity` 라벨도 갖고 있었고, **11행 전부 방향 일치**(party→loud, calm→quiet).
  `energy_full` 평균도 party 0.847 vs calm 0.136으로 report/02와 동일하게 깨끗이 갈림
  (`src/method-1/check_party_intensity_overlap.py`). **결론: party는 독립 축이 아니라
  intensity의 하위집합 — 별도 축으로 승격하지 않고, 신규 ground truth 라벨링·스크리닝
  대상에서 제외한다.**

### 2b. 실험 방법
1. 1단계에서 확정된 축마다 필요한 라벨 형식을 정한다(이분 라벨 vs 1~5 척도 — 기존
   intensity/brightness/party는 이분 라벨이었다. 이분 라벨은 채점이 빠르지만 통계적 힘이
   약하므로, 신규 축은 가능하면 척도형으로 수집해 향후 상관분석의 검정력을 확보한다).
2. 축마다 표본을 뽑는다 — 무작위 661곡 중 표집이 아니라 **극단층 우선 표집**(기존 audit·
   mood_warmth가 쓴 방식과 동일: 후보 신호 상으로 극단에 있는 곡을 먼저 라벨링하면 적은
   표본으로도 방향성 판정이 가능하다).
3. `data/ground_truth_labels.csv`에 신규 축을 이어붙이거나(같은 long-format 유지), 척도형
   라벨이 필요하면 별도 CSV로 분리한다(`out/ground_truth_<axis>.csv`).
4. 여유가 되면 축마다 라벨러 2인 이상을 확보해 일치도(Cohen's kappa 등)를 낸다 — "사람도 못
   가르는 축"과 "가를 수 있는데 신호가 없는 축"을 구분하기 위해 필요하다(현재 65행은 라벨러
   인원 미확인이라 이 구분이 안 됨, `vector_embedding/report/02` §7).

### 2c. 평가 방법
라벨 자체에 정오는 없다(사람 판단이 곧 ground truth). 다만 라벨링 완료 후 축별 표본 크기·
클래스 균형(예: bright 8 vs dark 8처럼 균형이 맞는지)을 점검해, 3단계 스크리닝에 쓰기에
충분한지(경험상 극단층 표본 20곡 이상, 양극단 균형 필요) 확인한다.

### 2d. 후보곡 준비 완료(2026-07-22) — 청취만 남음

극단층 표집(2b-2)까지 청취 없이 끝내뒀다. 다음 세션은 아래 두 CSV의 빈 채점 칸만 채우면
된다:

- **`out/valence_candidates.csv`**(33곡: mode_score 극단 30곡, 밴드당 최대 3곡 + 기존 반례
  앵커 3곡) — `valence_rating_1to10`에 0(매우 슬픔/처연)~10(매우 밝음/기쁨) 채점.
  앵커 3곡(375/111/109)은 이미 report/02에서 "사용자 인상은 밝음(9~10점)인데 mode_score는
  하위"로 알려진 곡 — 채점 후 실제로 높게 나오는지 재확인 겸용.
- **`out/pathos_candidates.csv`**(29곡, `mood_warmth/candidates_worksheet.csv` 재사용) —
  `pathos_rating_0to10`에 "애절하나 위로되는가"(0=전혀 위로 안 됨/황량, 10=애절하며 위로됨)
  로 채점. `prior_*` 컬럼은 예전 질문(esora 유사도) 참고용이라 새 채점에 참고하되 그대로
  베끼지 않는다.

생성 스크립트: `src/method-1/build_valence_candidates.py`, `build_pathos_candidates.py`
(둘 다 재실행 시 CSV를 덮어쓴다 — 이미 채점을 시작했다면 재실행 전 백업할 것).

> **⚠️ 2026-07-22 갱신 — 아래 §2e로 측정 방식 전환.** valence·pathos를 각각 단일 0~10
> 척도로 채점하는 위 방식은 **보류(파기 아님)**한다. 사용자가 학술적으로 검증된 GEMS
> (Geneva Emotional Music Scale) 도구로 처음부터 다시 시작하기로 결정했다 — 이유는
> 단일 척도가 `mood_warmth`에서 이미 걸렸던 함정(드라마틱함과 애절함이 한 척도에 뒤섞임)을
> 반복할 위험이 있고, GEMS-9는 그 함정을 항목을 쪼개는 것으로 구조적으로 피하기 때문.
> `valence_candidates.csv`/`pathos_candidates.csv`는 미래에 재사용할 수 있어 남겨두되,
> 현재 활성 트랙은 §2e다.

### 2e. GEMS-9 파일럿 설계 (2026-07-22 방법론 전환)

**측정 도구**: 사용자가 정리한 `notes/gems_methodology.md`(GEMS, Zentner et al. 2008 기반)를
그대로 따른다. 9개 항목(wonder·transcendence·tenderness·nostalgia·peacefulness·power·
joyful_activation·tension·sadness) 각각을 5점 리커트로 개별 채점 — 단일 valence/pathos
척도를 이 9항목 체크리스트로 대체한다. 3개 상위요인(Sublimity=wonder·transcendence·
tenderness·nostalgia·peacefulness, Vitality=power·joyful_activation, Unease=tension·
sadness)은 사후 분석(§3)에서 참고하되 미리 전제하지 않는다.

**표본 계획(gems_methodology.md §2)**: 1단계 n=1(사용자 본인) 파일럿 — 통계적 유효성은
없고 질적 방향 확인 용도. 유효하다고 판단되면 2단계로 n≥20 확대(최소 통계 기준).

**자극곡 선정(밴드 편중 방지)**: `src/method-1/build_gems9_pilot_candidates.py`가 밴드당
최대 3곡을 뽑되, **밴드 내 `energy_full`(이미 검증된 강도축) 최저/중간/최고**로 선정해
n=1 파일럿에서도 그 밴드의 감정 폭이 최대한 드러나게 한다(무작위 선정이 아님). 20곡 이상
표본인 10개 실제 밴드는 3곡씩, 5곡 이하 소규모 카테고리(various_artists 등)는 있는 만큼만
— 총 35곡(`out/gems9_pilot_candidates.csv`).

**대표구간 선정(gems_methodology.md §3.2)**: 대중가요/록 장르 기준 코러스(후렴구) 30초
내외(15~45초). **선정 주체는 사용자** — CSV의 `excerpt_start_sec`/`excerpt_end_sec`는
빈 칸으로 준비돼 있고, 사용자가 직접 듣고 채운다.

**설문 안 한 나머지 곡(661−35곡)의 처리 — 중요, §3과 연결**: 이 파일럿은 GEMS 점수를 661곡
전체에 직접 부여하지 않는다. 표본 35곡의 GEMS 점수를 **정답(ground truth)** 삼아 §3에서
기존 오디오 피쳐(energy_full·mfcc_*·mode_score 등, 이미 661곡 전체 계산됨)와 항목별로
대조하고, 예측력이 확인된 피쳐가 있으면 그 피쳐→GEMS점수 매핑을 나머지 626곡에 적용해
전체 커버리지를 얻는다. **어떤 피쳐도 특정 항목을 못 맞히면, 그 항목은 표본 35곡 안에서만
값이 존재하고 661곡 전체로 확장 불가** — 이 경우 그 항목은 시나리오 A(§4 참조)에서 탈락한다.
즉 이 파일럿의 실질 목적은 "GEMS 항목별 사람 인상 자체"보다 **"그 인상을 오디오로 예측
가능한지"**를 가리기 위한 정답지 생성이다.

**시나리오 결정(사용자 지시, 2026-07-22)**: 두 가지 활용 시나리오 중 **A를 먼저 시도**한다.
- **시나리오 A(우선)**: GEMS-9에서 유효성이 확인된 항목(들)로 `energy` 하드필터를
  **대체**한다. 기존에 검토했던 "계층적 구조(intensity 하드필터 유지 + 새 축은 소프트
  정렬)" 권고는 이번 라운드에선 보류한다 — 사용자 판단: 이전에 실패한 축(mode_score,
  가사 late-fusion)은 학술적 근거 없는 임시 지표였던 반면 GEMS는 검증된 척도라 같은
  전례로 취급하는 건 비약이라는 입장.
- **시나리오 B(대안)**: A가 §3에서 입증되지 못하면(어떤 GEMS 항목도 오디오 피쳐로 661곡에
  확장 불가), 에너지와 병행(부분/전체 결합)하는 구조로 재검토한다. 이때는 §4a의 계층 구조
  권고(하드필터+소프트정렬, 가중합 금지 — `report/04`의 late-fusion 실패 참조)를 다시
  적용한다.
- **항목별 개별 판정**: 9개 항목을 뭉뚱그려 "GEMS가 유효한가"로 판정하지 않는다. §3c 기준
  으로 항목마다 따로 통과/기각하고, 통과한 항목만 A로 승격한다.

생성 스크립트: `src/method-1/build_gems9_pilot_candidates.py`.

## 3. 후보 신호 전수 스크리닝

### 3a. 용어 정리
- **후보 신호**: 이미 661곡 전체에 대해 계산돼 있는 컬럼/피쳐 전부. 새로 계산하지 않는다.
  - `audio_feats.csv`: `energy_full`, `mode_score`, `mfcc_*`, `contrast`, `key`/`camelot`,
    `tempo`/`final_bpm` 계열
  - `mood_warmth/vocal_features*.csv`: `jitter_local`, `shimmer_local`, `hnr_mean`,
    `f0_median/range/std_st`, `vocal_centroid`(단, valence 대리축 c3는 **이미 2026-07-18
    null로 종결** — 재스크리닝 대상에서 제외하고 "검증 완료(실패)"로 표기)
  - `vector_embedding/src/method-1/out/song_profiles.csv`: 가사 임베딩·요약문
- **스크리닝 지표**: 라벨이 이분(binary)이면 그룹별 평균 차(§`report/02` 방식) 또는
  Mann-Whitney U, 라벨이 척도형이면 Spearman ρ.

### 3b. 실험 방법
1. 축마다, 2단계에서 확보한 라벨과 위 후보 신호 목록 전체를 **한 스크립트에서 일괄 대조**한다
   (신호 하나마다 별도 세션·별도 실험으로 쪼개지 않는다 — `report/02`가 15분에 끝낸 것과 같은
   저비용 스크리닝이 핵심이다).
2. 결과를 표 하나로 정리한다: 축 × 후보신호 매트릭스, 각 셀에 상관계수/평균차와 유의성.
3. 이미 검증 완료로 알려진 조합(예: intensity–energy_full=유효, valence–mode_score=유효하나
   부적합, valence–vocal c3=null)은 재실행하지 않고 기존 문서를 인용해 매트릭스에 그대로
   채워 넣는다 — 중복 실험 금지.

### 3c. 평가 방법
- **통과 기준**: `vector_embedding/report/02`가 쓴 기준을 그대로 채택 — 그룹 분리가 라벨 방향과
  일치하고(예: loud > quiet), 부호가 뒤집히지 않을 것. 척도형 라벨엔 |Spearman ρ| ≥ 0.4를
  잠정 기준으로 쓴다(`mood_warmth` 1라운드가 쓴 채택 기준과 동일선상 — 통일성 유지).
- **통과 못 함**: 그 축엔 현재 후보 신호 중 쓸 게 없다는 뜻. 4단계로 넘어가 구조적 대안을 검토
  한다(새 피쳐 개발은 최후 수단).
- **다중비교 주의**: 축 하나에 후보 신호가 여러 개면 우연히 유의해 보이는 경우가 생길 수 있다
  — BH-FDR 보정(`mood_warmth` 1라운드가 쓴 방식)을 병기한다.

## 4. 파이프라인 연결 및 실사용 검증

### 4a. 실험 방법

**GEMS-9 트랙(§2e)은 시나리오 A/B 결정을 따른다(사용자 지시, 2026-07-22 — §2e 참조)**:
1. §3에서 항목별로 통과한 GEMS 축이 하나 이상이면 **시나리오 A**부터 시도 — `energy`
   하드필터를 그 축(들)으로 대체해 `build_setlist()`에 연결.
2. §4b 실사용 검증(아래)에서 시나리오 A가 현재 배포판(에너지 단독) 대비 개선되지 않거나
   악화되면, **시나리오 B**(계층 구조: intensity 하드필터 유지 + GEMS 축은 소프트 정렬)로
   전환 — 이때는 `llm_param_control_separate/report/02`의 Stage C→A 순서 반전 설계를
   재사용하고, 가중합(linear combination) 방식은 쓰지 않는다(`vector_embedding/report/04`의
   late-fusion 실패 — 미검증 축이 검증된 축의 신호를 덮어씀 — 재발 방지).
3. §3에서 어떤 GEMS 항목도 통과하지 못하면(661곡 전체로 확장 불가, §2e), 시나리오 A·B 둘 다
   보류하고 두 대안을 검토한다:
   - **(a) 구조적 회피**: 그 축에 대한 사용자 요청은 LLM이 명시적으로 "정확한 매칭 불가"를
     인지하고, 다른 검증된 축(intensity 등)으로만 제약을 걸고 그 안에서 무작위/가사 소프트
     정렬에 맡긴다 — 거짓으로 맞는 척하지 않는다.
   - **(b) 신규 데이터 확보**: 오디오 피쳐가 아니라 완전히 다른 소스(상업 음성감정분석 API,
     추가 사람 라벨링 확대)를 검토한다. 이 폴더의 새 피쳐 개발이 아니라 별도 하위 트랙으로
     분리한다.
4. 연결된 파라미터로 실제 `build_setlist()` 프로덕션 코드에 다시 얹어 `selection_pipeline`
   방식(v1~v3 스냅샷·블라인드 A/B)으로 검증한다. v3가 이미 확인한 검정력 부족 문제
   (arm당 n=24는 부족, 82~85 필요)를 반복하지 않도록 처음부터 표본 크기를 검정력 계산으로
   정한다.

### 4b. 평가 방법
`selection_pipeline/report/03`·`note/stat_arm1vs2.md`가 쓴 것과 동일한 통계 절차
(쿼리 단위 대응비교 Wilcoxon signed-rank, 사전 검정력 계산으로 표본 크기 결정)를 그대로
재사용한다 — 새 판정 기준을 발명하지 않는다.

## 레퍼런스
- `notes/gems_methodology.md`(사용자 작성, GEMS 실험·설문 설계 표준 — §2e 근거)
- Zentner, Grandjean & Scherer (2008), "Emotions evoked by the sound of music: characterization,
  classification, and measurement", *Emotion* — GEMS-9/25/45 원 논문
- `audio_feats_analysis/report/10-key-detection-research-wrapup.md` §4 (탑다운 전환 문제제기 원문)
- `vector_embedding/report/02-acoustic_feature_audit.md` (스크리닝 방법론의 원형)
- `vector_embedding/report/03-lyrics_acoustic_association.md`, `report/04-lyrics_acoustic_fusion.md`
- `mood_warmth/README.md`, `mood_warmth/ROUND2-valence-proxy-DESIGN.md` (보컬 발성 valence 시도 종결)
- `selection_pipeline/DESIGN_v3.md`, `report/03-selection_pipeline_v3_method_comparison.md`,
  `note/stat_arm1vs2.md`
- `llm_param_control_separate/report/02-mood-lyrics-axis-design-review.md`
