# selection_pipeline 실험 설계서 — 선곡 파이프라인 3-way 비교
## (프로덕션 절대강도 매칭 vs 가사후보추림+절대강도 vs 가사후보추림+밴드상대백분위)

> **위치와 성격**: `topic/vector-embedding`의 하위 method가 아니라 **별개 주제**다. 가사 임베딩은
> arm 2·3에서 후보군을 좁히는 재료로만 쓰이고, RQ는 "선곡 파이프라인 구조(후보추림+강도해석)"이지
> "가사 벡터 검색"이 아니다 — `mood_warmth`·`chord_progression`처럼 vector-embedding의 산출물
> (`BAAI/bge-m3` 임베딩, `intensity` 등)을 **재사용하는 소비자**일 뿐이다. 아래 경로는 모두
> 저장소 루트 기준 전체경로로 표기한다(예: `topic/vector-embedding/src/method-2/...`).
>
> **배경**: `topic/vector-embedding/report/05-energy_distribution_by_band.md`가 프로덕션
> `selection.py`의 구조적 갭을
> 지적했다 — Stage A는 강도(intensity)를 **전역 절대값**으로 `|energy-target|≤0.08` 매칭하는데,
> 밴드마다 강도 분포가 전혀 달라(mygo 중앙값 0.360 vs mutype 0.765) 저텐션 꼬리(<0.1, 14곡)가
> 사실상 도달 불가하다. 그 리포트는 "밴드 상대 백분위" 대안을 **제안만** 하고 미착수로 남겼다.
> 이 연구는 그 제안을 실측으로 검증하고, 동시에 연구자가 새로 제기한 구조적 아이디어
> ("가사로 후보군을 먼저 추리고, 그 안에서 강도로 정렬/추출")를 함께 비교한다.
>
> **Phase 2(`topic/vector-embedding/src/method-2`)와의 차이 — 중요**: Phase 2의 결합(arm C)은
> 가사 백분위와 음향 백분위를 **가중합(α=0.5)**해 하나의 점수로 섞었고, 이 복합 점수(`acou_match`)가
> 만족도와 ρ=−0.588로 **유해**했다(`topic/vector-embedding/report/04-lyrics_acoustic_fusion.md`
> 결론). 이번 arm 2·3은 그 구조가 아니다 — **가사는 후보군을
> 좁히는 필터로만 쓰고, 최종 정렬/추출은 검증된 강도(intensity) 단일 축**으로 한다(가중합 없음).
> 오염원이었던 밝기/LLM목표매핑을 아예 배제한 구조라, Phase 2의 실패 원인이 재현되지 않을
> 것으로 예상한다 — 단 이는 가설이며 이번 연구가 검정한다.
>
> **구현자는 이 문서만 보고 코드를 작성한다.**

---

## 0. 연구 질문과 판정 기준 (사전 등록 — 채점 후 변경 금지)

**RQ1(주)**: 가사 기반 후보 추림을 도입하면(arm 2/3), 가사 없이 강도만 쓰는 현재 프로덕션 방식
(arm 1)보다 사용자 만족도가 개선되는가?

**RQ2(주)**: 후보군 내에서 강도를 **밴드 상대 백분위**(arm 3)로 해석하면, **절대값**(arm 2)보다
나은가 — 그리고 그 우열이 "밴드를 명시했는가"에 따라 갈리는가(= report05가 제안한 분기 로직의
실측 검증)?

**사전 등록 예측** (카테고리별, §2 참조):
| 쿼리 카테고리 | 예측 |
|---|---|
| 밴드 지정 + 상대 감성("이 밴드에서 가장 잔잔한/신나는") | **arm3 > arm2 ≥ arm1** — 프로덕션(arm1)은 밴드필터 내에서도 절대강도라 그 밴드의 실제 저텐션 곡에 못 미칠 수 있음 |
| 밴드 미지정 + 전체카탈로그 절대 표현("진짜 조용한 노래") | **arm1·arm2 ≥ arm3** — 상대 백분위를 여러 밴드에 걸쳐 쓰면 "조용함"의 절대적 의미가 깨짐(`topic/vector-embedding/report/05-energy_distribution_by_band.md` 트레이드오프) |
| 상황/기능성(가사 신호 약함) | 예측 없음(탐색) — 가사 후보추림이 관련 없는 곡을 걸러내 도움이 될 수도, 반대로 약한 가사 신호가 좋은 후보를 잘못 배제할 수도 있음 |
| 밝기 재확인(신규 표현, T1~T3 재사용 아님) | 예측 없음(탐색) — Phase 2 A4(`mismatch_query`↔만족도 ρ=−0.382)의 재현 여부 확인용 |

**판정표**:
| 판정 | 조건 |
|---|---|
| **구조 채택(가사 후보추림 유지)** | arm2 평균 **> arm1 평균**(전체) |
| **구조 기각(프로덕션 유지)** | arm2 평균 **≤ arm1 평균** — 이 경우 arm3 성적과 무관하게 가사 후보추림 자체를 보류 |
| **분기 로직 채택(arm3 부분 도입)** | 구조가 채택된 상태에서, "밴드 지정" 카테고리 한정 arm3 평균 **> arm2 평균**, **그리고** "밴드 미지정" 카테고리에서 arm3가 arm2보다 **뚜렷이 나쁘지 않음(평균차 ≤0.5)** → report05의 "밴드 명시 시 상대, 아니면 절대" 분기를 프로덕션에 반영 권고 |
| **분기 로직 기각** | 위 조건 불충족 — arm2(절대값 고정)만 채택 |

**사전 선언한 한계**:
- 쿼리 8개·평가자 1인 → **방향성 탐색**, 확증 아님(Phase 1·2와 동일 원칙).
- 후보 pool 크기 N(§3)은 사전 고정값이며 튜닝하지 않는다 — 결과가 애매해도 N을 사후에 바꾸지 않는다.
- 이 연구는 Stage A(SELECT)만 다룬다. Stage B(하모닉 시퀀싱·경계 연속성)는 범위 밖 —
  가사·강도축 비교라는 RQ에 하모닉/밝기버킷 변수를 섞으면 원인 분리가 안 되기 때문(의도적 축소,
  Phase 2 D2와 같은 논리).

---

## 1. 세 파이프라인의 정확한 정의

### 공통 입력
- LLM이 자연어 쿼리에서 **`intensity_target`(0~1, 661곡 백분위 목표)** 와 **`band_filter`(밴드
  태그 1개 또는 NA)** 를 추출한다. 프롬프트는 `topic/vector-embedding/src/method-2/DESIGN.md` §3의
  `INTENSITY` 축 정의를 그대로 승계(음량/밀도, 감정 아님을 명시)하고, `BAND`는 카탈로그 밴드 태그
  11개 중 하나 또는 `NA`로 강제한다. 모델은 `topic/vector-embedding/src/method-1/config.py`의
  `GROQ_MODEL`(현재 `meta-llama/llama-4-scout-17b-16e-instruct`) — **`openai/gpt-oss-20b`
  절대 금지**(배포 모델).
- `eligible_pool` = `topic/vector-embedding/src/method-1/full_catalog_songs.csv` 661곡 중
  `band_filter`가 있으면 그 밴드만(프로덕션 `build_setlist`의 band_filter 적용 순서와 동일 —
  후보추림보다 먼저 적용).
- `intensity`/`intensity_pct`는 `topic/vector-embedding/src/method-2/out/song_acoustics.csv`를
  그대로 재사용(재계산 금지 — 이미 검증된 값, `topic/vector-embedding/src/method-2/DESIGN.md` §2).
- `band_pct(곡)` = 그 곡의 **자기 밴드 population**(`eligible_band==True`인 동일 밴드 전체) 내
  `intensity` 백분위. `topic/vector-embedding/report/05-energy_distribution_by_band.md`의 표
  (밴드별 하위 20% 절대값 등)와 동일한 계산 방식.

### Arm 1 — 프로덕션 재현 (가사 미사용)
`src/backend/app/domain/selection.py`의 `Stage A` 로직을 **단일 목표**로 단순화해 재현
(Stage B 시퀀싱·밝기버킷 tie-break는 §0 한계에서 밝힌 대로 범위 밖 — 순수 강도 window만 재현):

```
window = { s in eligible_pool : |s.intensity - intensity_target| <= 0.08 }
if len(window) >= K:
    candidates = window (intensity 근접순 정렬)
else:
    candidates = eligible_pool 전체를 intensity 근접순 정렬  # 프로덕션의 fallback과 동일
top-K = candidates[:K]
```

가사 신호 전혀 사용 안 함 — 이것이 배포 중인 실제 동작이다.

### Arm 2 — 가사 후보추림 + 절대 강도
```
candidate_pool = top-N(eligible_pool, lyric_cosine 내림차순)   # §3 참조
window = { s in candidate_pool : |s.intensity - intensity_target| <= 0.08 }
if len(window) >= K: candidates = window (intensity 근접순)
else: candidates = candidate_pool 전체 (intensity 근접순)      # arm1과 동일한 fallback 규칙
top-K = candidates[:K]
```

### Arm 3 — 가사 후보추림 + 밴드 상대 백분위
Arm 2와 candidate_pool은 동일. 정렬 기준만 교체:
```
window = { s in candidate_pool : |s.band_pct - intensity_target| <= 0.08 }
(이하 arm 2와 동일한 fallback 규칙, band_pct 기준)
```
`band_pct`는 §1 공통 정의대로 **후보군이 아니라 그 곡이 속한 밴드 전체 population**에서 계산한
값을 그대로 쓴다(candidate_pool 내부에서 재백분위화하지 않음 — 후보군마다 표본이 달라지면
"밴드 내 몇 %"라는 의미 자체가 흔들리기 때문).

**K(top-K) = 3** (Phase 1·2와 동일한 관례 승계).

---

## 2. 쿼리 세트 (신규 8개 — T1~T3 재사용 금지)

기존 `STAGE2_QUERIES`(행복한/슬픈/꿀꿀해/신나는/위로/자장가)는 전부 "감정 서술문" 한 범주에
몰려 있어 이번 RQ(밴드별 강도 편차, 가사 후보추림의 순기능/역기능)를 가르지 못한다. 새 카테고리:

| id | 카테고리 | 쿼리 | 겨냥 |
|---|---|---|---|
| Q1 | 밴드지정+상대감성 | "mygo 노래 중에 제일 잔잔한 곡 틀어줘." | arm3 우위 예측 — mygo 자체가 저텐션 밴드라 절대매칭도 어느정도 통할 수 있음(약한 대비) |
| Q2 | 밴드지정+상대감성 | "raise a suilen 노래 중에 그나마 차분한 곡 틀어줘." | arm3 우위 예측(강한 대비) — RAS는 고텐션 밴드라 절대 TOL(0.08) 창에 "차분함"이 존재 안 할 가능성 큼(`report/05`: RAS 하위20%=0.57) |
| Q3 | 밴드미지정+절대강도 | "장르 상관없이 진짜 조용하고 힘 뺀 노래 틀어줘." | arm1·2 우위 예측 — 상대백분위를 전역에 쓰면 "조용함"의 의미가 깨질 것 |
| Q4 | 밴드미지정+절대강도 | "빵빵 터지는 하이텐션 파티 노래로만 채워줘." | 동일 논리, 고강도 쪽 |
| Q5 | 상황/기능성 | "운동할 때 들으면 힘 나는 노래." | 가사 신호 약함 — 가사 후보추림이 관련 없는 서정곡을 걸러 도움 되는지 |
| Q6 | 상황/기능성 | "새벽에 혼자 있을 때 듣고 싶은 노래." | 동일 논리, 저텐션+정서 혼합 |
| Q7 | 밝기 재확인(신규 표현) | "듣고 나면 기분이 조금 나아지는 노래." | Phase 2 A4(`mismatch_query`) 재현 확인용, 기존 문구와 다르게 표현해 앵커링 방지 |
| Q8 | 밝기 재확인(신규 표현) | "마음이 무겁고 가라앉는 밤에 어울리는 노래." | 동일 논리, 반대 극 |

밴드 태그는 `topic/vector-embedding/src/method-1/full_catalog_songs.csv`의 실제 값(`mygo`,
`raise_a_suilen` 등)과 정확히 일치시켜
LLM `BAND` 추출 프롬프트에 카탈로그를 인지시킨다.

---

## 3. 가사 후보추림 (arm 2·3 공통)

`topic/vector-embedding/src/method-1/06_stage2_search.py`의 방식을 **그대로 재사용**한다 —
새로 설계하지 않는다:
1. LLM으로 쿼리를 2~3문장 서술로 확장(`06_stage2_search.py`의 `expand_prompt` 템플릿 그대로).
2. `BAAI/bge-m3`로 확장문과 `topic/vector-embedding/src/method-1/out/song_profiles.csv`의
   `desc`를 임베딩, 코사인 유사도.
3. **`candidate_pool` 크기 N (사전 고정, 결과를 본 뒤 바꾸지 않음)**:
   `N = max(15, ceil(0.20 * len(eligible_pool)))` — eligible_pool(밴드필터 적용 후)의 상위 20%,
   단 밴드필터로 pool이 작아져도 최소 15곡은 확보(예: ave_mujica 29곡 → 20%=6이면 15로 올림).
   밴드 미지정 쿼리는 661곡의 20% ≈ 132곡.

산출물 `out/query_lyric_candidates.csv`: `query_id, tag, band, lyric_cosine, rank_in_pool`.

---

## 4. 블라인드 평가

### 4a. 점수 척도 (연구자 확정, 2026-07-18)
**1~5 Likert**: 1=전혀 일치하지 않는다 … 5=상당히 일치한다("이 곡이 이 요청과 얼마나 어울리는가").
0~10은 Phase 2에서 "필요 이상으로 넓었다"는 피드백으로 폐기.

### 4b. 시트 구성
1. arm 1/2/3 각각 top-3 → `(query_id, tag)` 쌍의 **합집합**(중복 제거). 세 arm의 candidate_pool이
   상당 부분 겹칠 것으로 예상되므로(§0 한계에 명시) 실제 고유 쌍은 8×9=72보다 훨씬 적을 것.
2. 무작위 셔플(`random.Random(20260717)`, Phase 2와 동일 시드 관례 승계).
3. `arm`·`rank`·`lyric_cosine`·`intensity`·`band_pct` 등 정체 노출 컬럼 전부 제거.

산출물:
- `out/method3_blind_sheet.csv` — `eval_id, query_id, prompt_text, band, song, url, score, comment`
  (`score`/`comment` 빈 칸, 연구자가 직접 채움)
- `out/method3_blind_mapping.csv` — `eval_id, query_id, tag, arms(|-결합), intensity, band_pct,
  intensity_target` (**언블라인드용, 채점 전 열지 말 것**)

### 4c. 청취 부담 관리
Phase 2의 D13 실수(설계 29곡 예고 vs 실제 47곡)를 반복하지 않기 위해, **05번 스크립트가 실제
고유 쌍 수를 산출한 직후 연구자에게 먼저 보고**하고(코드가 `print`로 정확한 수를 출력),
청취 착수는 그 숫자를 본 뒤 진행한다.

---

## 5. 구현 산출물 (파일 목록)

`topic/selection_pipeline/` 아래:

| 파일 | 역할 |
|---|---|
| `config.py` | 경로·`GROQ_MODEL`(method-1 승계)·`QUERIES`(§2)·`K=3`·`TOL=0.08`·`SEED=20260717` |
| `01_query_targets.py` | §1 공통입력 — LLM으로 `intensity_target`·`band_filter` 추출 → `out/query_targets.csv` (연구자 검토 체크포인트: NA/밴드 추출이 상식적인지) |
| `02_band_percentiles.py` | §1 `band_pct` 계산 → `out/song_band_percentiles.csv` (`tag, band, intensity, band_pct`) |
| `03_lyric_candidates.py` | §3 — `out/query_lyric_candidates.csv` |
| `04_run_arms.py` | §1 arm 1/2/3 실행 → `out/method3_arm_results.csv` (`query_id, arm, rank, tag, band, song, intensity, band_pct, lyric_cosine`) |
| `05_build_blind_sheet.py` | §4 — `out/method3_blind_sheet.csv`, `out/method3_blind_mapping.csv` (+ 고유 쌍 수 콘솔 출력) |
| `README.md` | 실행법 |

**공통 규칙**(Phase 1·2에서 확립, 그대로 승계): idempotent, 진행률 JSON,
`C:/Users/User/miniconda3/envs/warmth/python.exe` 직접 호출(`conda run` 금지, cp949),
`PYTHONIOENCODING=utf-8`, Groq 키는 `method-1/config.get_groq_api_key()` 패턴, ASR 가사 원문 관련
저작권 규칙은 이 method엔 해당 없음(가사 원문 미사용, `desc`만 재사용).

## 6. 실행 순서

```
01_query_targets.py     → intensity_target·band_filter 확인 (연구자 1회 검토)
02_band_percentiles.py  → band_pct 확인 (report05 표와 일치하는지 대조)
03_lyric_candidates.py  → candidate_pool 확인
04_run_arms.py          → 3 arm × 8쿼리 × top-3
05_build_blind_sheet.py → 블라인드 시트 (+ 고유 쌍 수 보고 → 청취 착수 여부 확인)
  ↓
연구자 청취·채점 (1~5)
  ↓
언블라인드 → §0 판정표 적용 → topic/selection_pipeline/report/01-selection_pipeline_comparison.md
```

## 7. 알려진 한계 (착수 시점에 이미 아는 것)

- 가사 임베딩 자체가 이 카탈로그에서 약한 신호임이 이미 확인됨(Phase 1: 가사단독 4.67~5.17/10).
  candidate_pool(top 20%)이 관련 곡을 걸러낼 위험이 구조적으로 존재 — Q5·Q6(상황/기능성)이
  이를 직접 테스트한다.
- N=20%는 임의값이다. 민감도 분석(N=10%/30%)은 이번 라운드 범위 밖 — 방향이 잡히면 후속 라운드로.
- 평가자 1인·쿼리 8개(§0에 이미 명시).
- Stage B(하모닉 시퀀싱) 배제는 SELECT 단계만 순수 비교하기 위한 의도적 축소이며, 실제 배포
  반영 시엔 Stage B와의 상호작용을 별도로 검토해야 한다.
