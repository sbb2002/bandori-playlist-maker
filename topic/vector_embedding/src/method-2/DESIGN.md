# method-2 실험 설계서 — 가사 × 음향 결합 검색 (late fusion)

> **이 문서의 목적**: Phase 1(`../method-1`, `report/01-lyrics_vector-searching.md`)의 결론
> "가사 임베딩의 실패는 쿼리 난이도가 아니라 **가사-곡조 불일치**에서 온다"를 받아, 음향 특성을
> 결합해 그 실패가 교정되는지 검증하는 실험 설계.
>
> **구현자는 이 문서만 보고 코드를 작성할 수 있어야 한다** — 여기 명시된 결정(모델명·파라미터·
> 스키마·상수)을 임의로 바꾸지 말고, 막히면 바꾸는 대신 질문할 것. Phase 1과 동일한 규칙이다.

---

## 0. 연구 질문과 판정 기준 (사전 등록 — 평가 전에 확정, 사후 변경 금지)

**RQ3 (주)**: 가사 임베딩에 **검증된** 음향 축을 late-fusion으로 결합하면, Phase 1에서 확인된
가사-곡조 불일치 실패가 교정되는가?

**RQ4 (부차)**: 세 가지 조건 중 무엇이 가장 나은가 — 가사 단독 / 음향 단독 / 결합?

**비교 기준선(baseline)**: **이번 라운드에서 블라인드로 재채점한 arm A의 평균.**
arm A는 Phase 1과 완전히 동일한 방법이므로(동일 임베딩·동일 쿼리, 검증 완료: 18/18쌍 일치)
가사 단독의 성능을 나타내며, **arm B·C와 동일한 채점 조건**에서 측정되므로 교락이 없다.
Phase 1의 **5.17/10**은 역사적 참조값으로만 쓴다(§5 정정 참조).

| 판정 | 조건 |
|---|---|
| **채택 후보** | 결합(C) 평균 **≥ 7.0** **그리고** C가 arm A보다 높음 **그리고** T1-Q2("슬픈 노래", Phase 1에서 0.3점) **≥ 5.0** |
| **조건부 재시도** | C가 arm A보다 높으나 7.0 미만 → 원인 분해(음향 축 부족/목표 매핑 오류/α) 후 재설계 |
| **기각** | C **≤ arm A** (가사 단독 대비 개선 없음) |

**부수 판정 (RQ4)**: arm B(음향 단독)가 arm C와 비슷하면 → "가사는 기여하지 않는다".
arm B가 arm A보다 높으면 → 이 카탈로그에서는 **음향이 가사보다 나은 신호**라는 뜻이며,
그 자체로 제품 함의가 크다(가사 파이프라인 전체가 불필요할 수 있음).

**재검사 신뢰도**: Phase 1과 겹치는 18쌍의 Phase 1 점수 vs 이번 블라인드 점수의 상관을 보고한다.
이 값이 낮으면(예: r < 0.7) **모든 arm 비교의 해상도가 그만큼 제한**되므로, 판정 전에 먼저 확인한다.

T1-Q2 조건을 별도로 건 이유: 전체 평균은 이미 잘 되던 쿼리(T1-Q1 9.7, T2-Q2 9.0)가 끌어올릴 수
있으므로, **이번 Phase가 표적하는 실패 사례가 실제로 고쳐졌는지**를 따로 못박는다.

**사전 선언한 한계** (결과와 무관하게 보고서에 유지):
- 쿼리 n=6, 평가자 1인 → 이번 라운드는 **확증이 아니라 방향성 탐색**이다. 통계적 유의성 주장 금지.
- α는 사전 고정한다(§4). 평가셋을 보고 α를 고르는 것은 과적합이므로 **금지**.

---

## 1. 배경 — 이 설계를 바꾼 사전 점검 (2026-07-17)

착수 전 `data/ground_truth_labels.csv`(65행: brightness 16 / intensity 36 / party 13,
사람이 붙인 정답 라벨)로 후보 음향 지표를 감사했다. 결과가 설계를 크게 바꿨으므로 근거를 남긴다.

### 1a. `energy` · `energy_proxy` 는 쓰면 안 된다 (확정)

라벨별 지표 평균 — **정답이라면 loud > quiet, party > calm 이어야 한다**:

| 지표 | intensity: loud(22) | quiet(14) | party: party(8) | calm(5) | 판정 |
|---|---|---|---|---|---|
| `energy` | 0.446 | 0.450 | 0.369 | 0.417 | **신호 없음** (구분 못 함) |
| `energy_proxy` | **-0.590** | **+0.336** | **-0.657** | **+1.399** | **부호 역전** |
| `energy_full` | **0.695** | **0.174** | **0.847** | **0.136** | **유효** (두 축 모두 강하게 분리) |
| `i_mean` | 0.377 | -0.129 | 0.547 | -0.297 | 유효 |

두 개의 독립적인 라벨 차원(intensity, party)이 같은 결론을 가리킨다. 이는 우연이 아니다.

**이것은 프로덕션 버그가 아니다** — 앱은 이미 알고 우회하고 있다. `src/backend/app/repo/song_repo.py`
docstring(main 브랜치)이 명시한다: *"`energy`(EMOI-MAP 펄스용)·`energy_proxy`·
`acousticness_proxy`는 발췌 구간만 반영 → 오판"*. 즉 이 컬럼들은 **곡 전체가 아니라 발췌 구간**에서
계산된 레거시 값이고, 앱은 적재 시점에 `energy_full`·`i_*` 기반 합성 지표를 따로 만들어 쓴다(§2).

→ **method-2의 실질적 위험은 이 레거시 컬럼을 순진하게 가져다 쓰는 것**이었다. 이 감사가 없었다면
"음향 결합은 효과 없음"이라는 **거짓 기각**에 도달했을 것이다.

### 1b. `mode_score` 는 유효하지만, valence(체감 감정가)가 아니다

| 지표 | brightness: bright(8) | dark(8) | 판정 |
|---|---|---|---|
| `mode_score` | **+0.352** | **-0.286** | 유효 |

라벨 분리는 깨끗하다. 그러나 Phase 1 채점 데이터와 대조하면 다른 그림이 나온다:

| 곡 | 쿼리 | 사용자 점수 | `mode_score` 백분위 |
|---|---|---|---|
| poppin_party__375 `Yes! BanG_Dream!` | "날아갈 것처럼 신나는" | **10** | **0.04** (최암부) |
| hello_happy_world__111 | "행복한 노래" | **9** | **0.24** |
| hello_happy_world__109 | "행복한 노래" | **10** | **0.39** |

프랜차이즈에서 가장 밝게 들리는 곡들이 `mode_score` 하위에 있다. 모순이 아니다 — `mode_score`는
**장/단조(major/minor) 축**이고, J-rock·애니송은 **단조로 밝고 신나는 곡**을 흔하게 쓴다.

→ **결론: 검증된 강도(intensity) 축은 확보했으나, 검증된 valence 축은 없다.** 이것이
"슬픈 노래"(Phase 1: 0.3점)가 실패한 구조적 이유일 가능성이 크다. §3에서 `brightness`를
장/단조 축으로만 취급하고, LLM이 이 축을 **"무관(NA)"으로 비활성화할 수 있게** 설계하는 근거다.

### 1c. 사전 점검 — 이 실험은 성립하는가

- **어둡고·저에너지·느린 곡이 카탈로그에 18곡 존재**(roselia 8곡 편중). top-3를 뽑기엔 충분 →
  "슬픈 노래"가 원리적으로 불가능한 요구는 아니다.
- Phase 1 채점(n=18) 회고 분석: 가사 cosine r=+0.335 / 음향 목표적합도 r=+0.368(단, 이 목표값은
  사후에 손으로 지정한 것이라 **낙관 편향** — 근거가 아니라 타당성 신호로만 취급).
  두 신호가 비슷한 크기이고 서로 다른 곡을 잡는다 → **결합에 여지가 있다**는 정도까지만 말할 수 있다.

---

## 2. 음향 축 구축 — 앱의 합성 로직을 이식한다

새로 발명하지 말 것. `src/backend/app/repo/song_repo.py`의 `load_songs()`가 이미
검증된 강도 지표를 만든다. **동일하게 재현**한다(향후 앱 반영 시 정합성을 위해서도 필수).

```
intensity(곡) = power_mean_p3( signals )
  signals = [
    percentile(-acousticness_proxy),   # 1 = 가장 비어쿠스틱(시끄러움)
    energy_full,                       # 0~1 원값 그대로 (백분위 변환 금지)
    percentile(i_min), percentile(i_mean), percentile(i_end),
  ]
  power_mean_p3(xs) = ( sum(x**3) / len(xs) ) ** (1/3)   # soft-OR: "하나라도 시끄러우면 시끄럽다"
```

**중요한 세부** (틀리면 값이 달라진다):
- 백분위의 모집단은 **`eligible_band == True` 인 행만**. 전체 661행이 아니다.
- 결측 컬럼·결측 값은 signals에서 **자동 제외**(리스트에 넣지 않음). `energy_full` 3건 결측 존재.
- `_INTENSITY_P = 3`.
- 백분위 산출 방식은 `song_repo._percentile_ranker`와 동일해야 한다 — 해당 함수를 그대로 읽어와
  이식할 것(직접 `rank(pct=True)`로 대체하면 tie 처리가 달라질 수 있음. 반드시 원본을 확인).

산출물 `out/song_acoustics.csv` (661행):

| 컬럼 | 정의 |
|---|---|
| `tag` | `{band}__{idx:03d}` — method-1 산출물과의 조인 키 (661/661 일치 확인됨) |
| `idx`, `band`, `song` | `songs_master.csv`에서 |
| `intensity` | 위 합성값 (0~1) |
| `intensity_pct` | `intensity`의 661곡 내 백분위 |
| `brightness_pct` | `mode_score`의 661곡 내 백분위 |
| `tempo_pct` | `bpm`의 661곡 내 백분위 |
| `shape` | 원값 (acoustic/neutral/bright/shimmer) — 분석용, 점수엔 미사용 |

**축을 더 늘리지 말 것.** 쿼리 6개로는 아무것도 적합시킬 수 없다. 검증된 3축(intensity,
brightness, tempo)만 쓴다.

---

## 3. 쿼리 → 음향 목표 매핑 (LLM, 고정 앵커 금지)

연구자의 기존 원칙 유지: **앵커를 손으로 고정하지 않는다.** 자연어 쿼리를 LLM이 음향 목표로 변환한다.
앱도 이미 LLM 쿼리 확장을 하므로 프로덕션에서 재현 가능한 구조다.

**입력**: `STAGE2_QUERIES`의 원문 6개 (method-1 `config.py`에서 그대로 복사 — 재작성 금지).

**출력 스키마** (정확히 이 형식, 다른 말 금지):
```
INTENSITY: <0.0~1.0 또는 NA>
BRIGHTNESS: <0.0~1.0 또는 NA>
TEMPO: <0.0~1.0 또는 NA>
```

**프롬프트 요건**:
- 각 축은 **661곡 카탈로그 내 백분위 목표**임을 명시(0.0=카탈로그에서 가장 낮음, 1.0=가장 높음).
- `INTENSITY` = 소리의 세기·밀도(조용함↔시끄러움). 감정이 아니라 **음량/밀도**임을 명시.
- `BRIGHTNESS` = **장조/단조 축**임을 명시. "밝은 감정"이 아니라 화성적 장단조.
  단조로도 신나는 곡이 흔하다는 점을 프롬프트에 넣어, LLM이 "행복=BRIGHTNESS 1.0"으로
  단순 매핑하지 않게 한다(§1b의 실패를 방지).
- `TEMPO` = BPM 백분위.
- **`NA`는 "이 축은 이 요청과 무관"** 이라는 뜻이며 적극 사용하도록 지시한다. 억지로 숫자를 채우면
  무관한 축이 점수를 오염시킨다.

**모델**: `meta-llama/llama-4-scout-17b-16e-instruct` (Phase 1 마지막에 쓴 모델, 할당량 여유).
**절대 `openai/gpt-oss-20b`를 쓰지 말 것 — 배포 백엔드가 쓰는 모델이다.**
`temperature=0`, 실패 시 최대 3회 재시도.

산출물 `out/query_acoustic_targets.csv`: `query_id, tier, prompt_text, intensity_t, brightness_t, tempo_t`
(NA는 빈 칸). **캐시**: 파일이 있으면 재호출하지 않는다(Phase 1과 동일한 idempotent 규칙).

---

## 4. 검색 arms 와 결합 방식

### 4a. 정규화 — 이걸 빠뜨리면 α가 무의미해진다

Phase 1 결과에서 가사 cosine의 실측 범위는 **0.658 ~ 0.720**(폭 0.06)로 극도로 압축돼 있다.
음향 적합도는 0~1 전폭을 쓴다. 두 값을 그대로 더하면 음향이 일방적으로 지배한다.

→ **양쪽 모두 661곡 pool 내 백분위(rank, 0~1)로 변환한 뒤 결합한다.**

### 4b. 점수

```
lyr_rank(곡)  = percentile( cosine(query_emb, desc_emb) )         # 661곡 내
acou_match(곡) = 1 - mean( |feature_pct - target| for 축 in NA가 아닌 축 )
acou_rank(곡) = percentile( acou_match )                           # 661곡 내
```
- 모든 축이 NA인 쿼리는 `acou_match = 0.5` 상수(중립) 처리하고 로그에 경고를 남긴다.
- 축 대응: `INTENSITY→intensity_pct`, `BRIGHTNESS→brightness_pct`, `TEMPO→tempo_pct`.

### 4c. arm 정의

| arm | 점수 | 비고 |
|---|---|---|
| **A** 가사 단독 | `lyr_rank` | **Phase 1과 동일** — 재실행하지 말고 `method-1/out/stage2_eval_sheet.csv`의 결과·점수를 그대로 가져온다 |
| **B** 음향 단독 | `acou_rank` | 가사 기여도를 재는 대조군. B가 C와 비슷하면 "가사는 기여 없음"이라는 중요한 결론 |
| **C** 결합 | `α·lyr_rank + (1-α)·acou_rank` | **α = 0.5 (사전 고정, 주 판정 대상)** |

**민감도 분석**: α ∈ {0.25, 0.75}도 top-3를 산출해 `out/phase2_alpha_sensitivity.csv`에 남긴다.
단 **평가·판정 대상은 α=0.5 뿐**이다. 나머지는 보고서에 "α를 흔들면 결과가 얼마나 흔들리는지"를
적기 위한 참고 자료이고, **채점 시트에 넣지 않는다**.

각 arm × 6쿼리 × **top-3**.

**가사 임베딩 재사용**: 곡 쪽 `desc` 임베딩과 쿼리 확장문은 Phase 1 산출물
(`method-1/out/stage2_queries_expanded.csv`, 임베딩 모델 `BAAI/bge-m3`)을 **그대로 재사용**한다.
arm A가 Phase 1과 완전히 동일해야 baseline 비교가 성립하므로, 쿼리 확장을 다시 LLM에 돌리지 말 것.

---

## 5. 블라인드 평가 시트

Phase 1은 arm 비교가 없어 비블라인드로도 문제없었다. **이번엔 arm을 비교하므로 블라인드가 필수**다 —
연구자는 자신의 Phase 1 점수를 기억하고 있어 앵커링 위험이 있다.

> **2026-07-17 정정 — 이 절의 초안(점수 승계안)은 치명적 결함이 있었다. 폐기한다.**
>
> 초안은 "Phase 1에서 이미 채점된 18쌍은 제외하고 점수를 승계"하려 했다(청취 부담 47→29곡).
> 그러나 구현 후 arm 구성을 확인하니 **arm A의 18쌍이 Phase 1의 18쌍과 정확히 일치**하고
> (동일 방법이므로 당연), **A∩B = 0쌍**이다. 즉 승계했다면:
> - arm A → 100% **비블라인드**(Phase 1) 점수
> - arm B → 100% **블라인드**(신규) 점수
>
> **arm과 채점 조건이 완전히 교락(confound)된다.** A vs B는 이 실험의 간판 비교인데,
> 그 차이가 방법의 차이인지 채점 조건의 차이인지 영영 분리할 수 없게 된다.
> 부담을 줄이려다 실험의 주 비교를 망칠 뻔했다.
>
> **채택안**: 47쌍 **전부 블라인드 재채점**. 부수 이득으로 Phase 1과 겹치는 18쌍이
> **재검사 신뢰도(test-retest)** 추정치를 준다 — 평가자 1인이 이 연구의 가장 큰 선언된 한계이고
> (`report/01`), 지금까지 그 잡음 수준을 몰랐다. 단 연구자가 곡을 기억하고 있어 신뢰도는
> **낙관 편향**된다(상한선으로만 해석할 것).

**구성 절차**:
1. arm A/B/C의 `(query_id, tag)` 쌍을 **합집합**으로 모은다 (최대 54쌍 → arm 간 중복 제거 후 47쌍).
2. **전 쌍을 채점 대상으로 한다.** Phase 1 점수는 승계하지 않는다(위 정정 참조).
   Phase 1 점수는 `method-1/out/stage2_eval_sheet.csv`에 그대로 두고, 분석 시
   **재검사 신뢰도 계산에만** 쓴다.
3. 47쌍을 **무작위 셔플**(`random.Random(20260717)` — 시드 고정, 재현성).
4. **arm·rank·점수·cosine 컬럼을 모두 제거**한다.

산출물:
- `out/phase2_blind_sheet.csv` — `eval_id, query_id, prompt_text, band, song, url, score, comment`
  (`score`/`comment`는 빈 칸. 연구자가 IDE에서 직접 채움. 0~10 정수)
- `out/phase2_blind_mapping.csv` — `eval_id, query_id, tag, arms, rank_A, rank_B, rank_C,
  lyr_rank, acou_rank, acou_match` (**언블라인드용, 분석 전까지 열지 말 것**)

`arms` 컬럼은 해당 쌍을 뽑은 arm들을 `|` 로 연결(예: `A|C`).

---

## 6. 구현 산출물 (파일 목록)

`topic/vector-embedding/src/method-2/` 아래:

| 파일 | 역할 |
|---|---|
| `config.py` | 경로·모델명·상수·`STAGE2_QUERIES`(method-1에서 복사)·`ALPHA=0.5`·`SEED=20260717` |
| `01_audit_features.py` | §1a 감사 재현 — `ground_truth_labels.csv` 대조표를 `out/feature_audit.csv`로 |
| `02_build_acoustics.py` | §2 — `out/song_acoustics.csv` |
| `03_query_targets.py` | §3 — `out/query_acoustic_targets.csv` (LLM, 캐시) |
| `04_fusion_search.py` | §4 — `out/phase2_search_results.csv`, `out/phase2_alpha_sensitivity.csv` |
| `05_build_blind_sheet.py` | §5 — `out/phase2_blind_sheet.csv`, `out/phase2_blind_mapping.csv` |
| `README.md` | ① 방법 소개 ② 실행법 (저장소 규칙) |

**공통 규칙** (Phase 1에서 확립, 그대로 승계):
- **진행률 JSON**: 오래 걸리는 단계(03, 04)는 `out/<step>_progress.json`에
  `{step, n_total, n_done, status, updated_at}`을 주기적으로 기록.
- **idempotent**: 산출 CSV가 있으면 이미 처리된 항목은 건너뛴다. 항목마다 캐시 저장.
- **저작권**: ASR 가사 원문은 **절대 커밋 금지**(`DESIGN.md` §3, method-1). `work/`는 gitignore.
  method-2는 원문을 다루지 않지만 규칙은 동일하게 적용.
- **실행 환경**: conda env `warmth`. Windows 콘솔 cp949 이슈 때문에 `conda run`을 쓰지 말고
  `C:/Users/User/miniconda3/envs/warmth/python.exe`를 직접 호출하고 `PYTHONIOENCODING=utf-8`를 설정.
- **Groq 키**: `config.get_groq_api_key()` 패턴을 method-1에서 그대로 가져온다
  (`work/groq.key` 폴백 포함). **키를 코드·커맨드라인에 절대 인라인하지 말 것.**

---

## 7. 실행 순서

```
01_audit_features.py   → 감사표 확인 (§1a 재현되는지)
02_build_acoustics.py  → song_acoustics.csv
03_query_targets.py    → 목표값 확인 (연구자 눈으로 1회 검토 — NA가 적절히 붙었는지)
04_fusion_search.py    → 3 arm × 6 쿼리 × top-3
05_build_blind_sheet.py→ 블라인드 시트
  ↓
연구자 청취·채점 (0~10)
  ↓
언블라인드 → arm별 평균 → §0 판정 기준 적용 → report/03-lyrics_acoustic_fusion.md
```

**03 이후 연구자 검토를 한 번 끼운다**: LLM이 뽑은 음향 목표가 상식적으로 말이 되는지
(예: "자장가" → INTENSITY 낮음, "신나는" → INTENSITY 높음, BRIGHTNESS는 NA일 수도) 눈으로 확인.
여기서 명백히 틀렸으면 프롬프트를 고치는 게 맞고, 그건 평가셋 과적합이 아니다(채점 전 단계).

---

## 8. 알려진 한계 (착수 시점에 이미 아는 것)

- **valence 축 부재** (§1b). 검증된 감정가 지표가 없다. `mode_score`는 장/단조일 뿐이다.
  "슬픈 노래"가 이번에도 실패하면, 원인은 결합 방식이 아니라 **feature 공간의 공백**일 가능성이 높다.
  → 그 경우 후속은 `topic/mood_warmth`의 발성 지표(f0_range_st, HNR, shimmer, 합성 c3)를
  661곡으로 확장하는 것이다. **보컬 스템은 Phase 1 ASR 준비 과정에서 661곡 전부 이미 확보돼 있어
  (`method-1/work/stems_full/htdemucs/`) 재분리 비용이 없다** — 이 라운드에선 범위 밖으로 두되,
  기각/조건부 판정 시 1순위 후속으로 둔다.
- **`mood_warmth` 1라운드 선례**: 그 연구는 "mode_score/energy로는 지각의 대부분이 미설명"으로
  끝났다. 단 그때의 `energy`는 §1a에서 **무효로 판명된 바로 그 컬럼**이다. 즉 그 null 결과는
  "음향이 무력하다"가 아니라 "깨진 컬럼을 썼다"로 재해석될 여지가 있고, 이번 라운드가 그걸 가른다.
- **평가자 1인·쿼리 6개** (§0에 사전 선언).
- **roselia 편중**: 어둡고 느린 곡 18곡 중 8곡이 roselia → "슬픈 노래" 결과가 roselia로 쏠릴 수
  있다. 밴드 다양성은 이번 판정 기준에 넣지 않되, 관찰되면 보고서에 기록한다.

---

## 9. 부속 연구 — 가사 감성 ↔ 음향 특성 연관 분석 (n=661)

> 연구자 제안(2026-07-17): *"음향학적 특성과 가사를 바탕으로 이해한 감성적 특성 간에 상관관계나
> 연관성이 있는지도 조사해. 나중에 설문 완료 후 이 상관관계와 사람 평가를 교차검증하면 뭔가 좋은
> 결과가 나올지도 모른다."*

**왜 가치가 있는가**: Phase 1의 핵심 발견("가사-곡조 불일치")은 **n=18의 정성 코멘트**에 기대고 있다.
이 분석은 같은 현상을 **n=661에서 정량화**한다. 사람 청취가 전혀 필요 없고(관찰 연구), §1~§5와
독립적으로 돌아가므로 설문 대기 중에 완료할 수 있다.

**RQ5**: 가사에서 유래한 감성 표현과 곡의 음향 특성 사이에 연관이 있는가? 없다면 두 신호는
직교하며, 이는 late-fusion의 근거를 강화하는 동시에 Phase 1 발견을 대규모로 확증한다.

### 9a. 데이터

| 쪽 | 출처 | 내용 |
|---|---|---|
| 가사 감성 | `method-1/out/song_profiles.csv` | `desc`(한국어 한 문장), `category1`, `category2` — 661곡 |
| 음향 | `out/song_acoustics.csv`(§2) + `data/songs_master.csv` + `data/full_audio_features.csv` | 아래 목록 |

**음향 변수 (연구자 요청대로 "모든 음향학적 특성"을 넣되, 역할을 구분한다)**:
- *검증됨*: `intensity`(§2 합성), `energy_full`, `i_mean`·`i_std`·`i_min`·`i_max`·`i_start`·`i_end`, `mode_score`, `bpm`
- *미검증·탐색적*: `acousticness_proxy`, `instrumentalness_proxy`, `harmonic_ratio`(있으면), `shape`(범주형)
- *직접 측정(librosa, `full_audio_features.csv`)*: `cen_mean`/`cen_p90`(스펙트럼 중심=밝기), `roll_*`,
  `bw_*`(대역폭), `flat_*`(평탄도), `contrast_*`, `zcr_*`, `perc_*`(타악 성분=리듬), `onset_mean`/
  `onset_p90`/`onset_rate`(리듬 밀도), `rms_mean`/`rms_p90`
- **음성 대조군(negative control)**: `energy`, `energy_proxy` — §1a에서 **무효/역전으로 판명된 컬럼**을
  일부러 포함한다. 이들이 가사 감성과 유의한 연관을 보인다면 그건 **분석 파이프라인의 오류 신호**다.
  통과 여부를 §9e에 명시적으로 보고한다.

**주의**: `full_audio_features.csv`는 **663행**(`songs_master.csv`는 661행)이다. 중복 업로드 2곡
(`idx` 525, 588)이 제거된 이력이 있다(커밋 `ead15e3`). `idx` 기준 inner join으로 661행에 맞추고,
탈락 행 수를 로그로 남길 것.

### 9b. 분석 A1 — 해석 가능한 감성 축 투영 (주 분석)

`desc`를 `BAAI/bge-m3`로 임베딩한 뒤, **앵커 단어쌍의 차이 벡터**에 투영해 해석 가능한 스칼라를 만든다.

```
axis_vec = mean(emb(positive_anchors)) - mean(emb(negative_anchors))
score(곡) = cosine( emb(desc), axis_vec )
```

| 축 | positive anchors | negative anchors |
|---|---|---|
| `lyr_valence` | 행복, 기쁨, 희망, 설렘, 사랑 | 슬픔, 절망, 우울, 고독, 상실 |
| `lyr_arousal` | 열정, 흥분, 질주, 격렬, 환호 | 평온, 차분, 잔잔, 고요, 나른함 |

차이 벡터를 쓰는 이유: Phase 1에서 bge-m3의 raw cosine이 0.658~0.720으로 극도로 압축돼 있었다.
차이 벡터는 공통 성분을 상쇄하므로 이 압축 문제를 회피한다.

각 감성 축 × 각 음향 변수에 대해 **Spearman ρ(주) + Pearson r(부)**. 음향 변수가 심하게
치우쳐 있으므로 순위 기반인 Spearman을 주 지표로 삼는다.

### 9c. 분석 A2 — 카테고리 그룹 대비 (해석용)

`category1` ∪ `category2`에서 **출현 n≥20인 키워드**만 추린다. 각 키워드 그룹 vs 나머지에 대해
음향 변수의 **Cohen's d + Mann-Whitney U**.

특히 **"슬픔·절망·우울" 계열 그룹 vs "행복·기쁨" 계열 그룹**을 명시적으로 대비한다 —
이것이 가사-곡조 불일치의 **직접 검정**이다. 두 그룹의 `intensity`·`mode_score`가 유의하게
다르지 않다면, "가사가 슬픈 곡과 밝은 곡이 음향적으로 구분되지 않는다"는 뜻이고,
Phase 1의 "슬픈 노래" 실패(0.3점)를 대규모로 설명한다.

### 9d. 분석 A3 — 예측 상한 (ceiling)

**"가사가 음향을 얼마나 아는가"의 상한**을 구한다. `desc` 임베딩(1024차원) → 각 음향 변수를
**Ridge 회귀, 5-fold 교차검증 R²**로 예측.

- **in-sample R² 보고 금지.** 1024차원 × n=661이면 in-sample R²는 무의미하게 1.0에 가깝다.
  반드시 out-of-fold 예측 기준. Ridge의 `alpha`는 **fold 내부에서** 선택(중첩 CV, 누수 방지).
- **두 가지 fold 전략을 모두 보고한다**:
  - `KFold(5, shuffle=True, random_state=SEED)` — 일반
  - `GroupKFold(5, groups=band)` — **밴드 누수 차단**
  같은 밴드 곡은 프로듀서·편곡 스타일을 공유한다. 가사에서 "아, roselia구나"를 알아채고 roselia의
  음향 프로필을 맞히면, 가사→사운드의 진짜 연결이 없어도 R²가 부풀려진다. **두 R²의 격차가
  곧 "밴드 정체성" 교란량**이며, 그 자체로 보고 가치가 있다.
- 역방향도 수행: 음향 변수 전체 → `lyr_valence` / `lyr_arousal` (동일 프로토콜).

**해석 가이드**: GroupKFold R² ≈ 0 이면 → 가사는 음향 정보를 사실상 담지 않는다 → 두 신호는
직교하며 **late-fusion의 근거가 최대화**되고 Phase 1 발견이 n=661에서 확증된다.

### 9e. 다중비교와 효과크기 — 이 분석의 가장 큰 함정

**n=661에서는 통계적 유의성이 싸다.** |ρ|≈0.11만 돼도 p<0.005다. 유의성만 보고 "연관이 있다"고
쓰면 안 된다.

- **FDR 보정**: Benjamini-Hochberg, 분석 패밀리(A1/A2)별로 각각 적용. q<0.05.
  (`topic/mood_warmth` 1라운드가 쓴 관례를 그대로 승계한다.)
- **효과크기 하한 사전 선언**: **|ρ| ≥ 0.2**(분산의 약 4%) 미만은 FDR을 통과해도
  **"연관 없음"으로 해석**한다. A2는 **|d| ≥ 0.3**.
- **음성 대조군 통과 조건**: `energy`·`energy_proxy`가 위 기준을 통과하면 파이프라인 오류를
  의심하고 원인을 규명하기 전까지 결과를 보고하지 않는다.

> **2026-07-17 게이트 발동 및 해소 — 음성 대조군 설계가 틀렸다.**
>
> A2에서 `자유` × `energy_proxy`(d=−0.4207, q=0.0224)가 기준을 통과해 위 조항이 발동했다.
> 규명 결과 **파이프라인 오류가 아니라 내 음성 대조군 설계의 결함**이다:
>
> 1. **`energy`·`energy_proxy`는 null 변수가 아니다.** §1a에서 "무효/역전"으로 판정한 것은
>    *지각 강도의 대리 지표로서* 무효라는 뜻이지, 아무것도 측정하지 않는다는 뜻이 아니다.
>    발췌 구간 에너지를 (부호가 뒤집힌 채) 실제로 측정한다. 따라서 가사 키워드와 **정당하게**
>    연관될 수 있다. (실제로 `energy_proxy`는 역전돼 있으므로 d=−0.42는 "자유 테마 곡이 지각적으로
>    더 에너제틱하다"는 뜻이고, 이는 그럴듯하다.) **부호가 틀린 지표는 null 대조군이 될 수 없다.**
> 2. **올바른 대조군은 순열이다.** 곡-키워드 배정을 셔플한 진짜 귀무분포(200회):
>    평균 **0.10** / 최대 **9**. 관측 **33**. → **p < 0.005, 진짜 신호.**
> 3. 보조 근거: A1 대조군 0/4 통과, A3에서 `energy_proxy`·`energy`의 GroupKFold R² =
>    −0.0212 / −0.0830 (예측력 없음).
>
> → **A2 결과를 확정한다.** 단 FDR q<0.05에서 36건 발견 시 **약 2건은 위양성이 기대**되므로
> 개별 히트를 단독으로 신뢰하지 말 것. 대조군 히트 1건은 정확히 이 기대 범위 안이다.
>
> **추가 검정 (밴드 매개 여부)**: 밴드 내 순열(밴드 구조 보존, 곡 수준 연결만 파괴) 귀무분포는
> 평균 **3.85** / 95%tile **12** / 최대 **26**. 관측 33은 이를 넘는다(p<0.005) → 연관은
> 밴드 매개만이 아니라 **곡 수준에도 존재**한다. 단 귀무 평균이 0.10 → 3.85로 **38배** 뛴 것
> 자체가 밴드 교란의 크기를 보여주며, A3의 kfold↔GroupKFold 격차(평균 +0.086)와 정합한다.

### 9f. 분석 A4 — 설문과의 교차검증 준비 (연구자 제안의 핵심)

곡별 **불일치 지표**를 사전에 계산해 저장해 둔다. 설문이 끝나면 이것과 사람 점수를 대조한다.

```
mismatch_arousal(곡) = | percentile(lyr_arousal) - intensity_pct |
```

`intensity`는 §1a에서 검증된 축이므로 이 지표는 근거가 탄탄하다.
**valence 쪽은 검증된 음향 축이 없으므로**(§1b) `mode_score`를 쓰되 **약한 대리 지표임을 명시**하고
`mismatch_valence_weak`로 이름 붙여 별도 취급한다.

**사전 등록한 예측**: 설문 완료 후, 사람 점수와 `mismatch_arousal` 사이에 **음의 상관**이 나타난다
(불일치가 클수록 만족도가 낮다). 이것이 확인되면 Phase 1의 정성적 발견에 **메커니즘 수준의 근거**가
생긴다. 확인되지 않으면 Phase 1의 해석 자체를 재검토해야 한다.

이 검정은 **설문 채점이 끝난 뒤에 수행**한다. 지금은 지표만 계산해 저장한다(`out/lyrics_acoustic_alignment.csv`).
지표 정의를 결과를 본 뒤에 바꾸는 것은 금지.

> **2026-07-17 보강 — `mismatch_arousal`이 불안정한 축에 의존한다. 주 지표를 교체한다.**
>
> §9h의 앵커 LOO 검사에서 **`lyr_arousal`이 사전 등록 기준을 미달**했다(변형 간 최소 상관
> **0.8998 < 0.90**). 기준선에서 0.0002 떨어진 아슬아슬한 미달이고, 각 변형과 전체 축의 상관은
> 0.9601로 양호하지만, **사전 등록은 사전 등록이다** — `lyr_arousal`을 신뢰하지 않는다.
> (`lyr_valence`는 0.9689로 통과.)
>
> 문제는 연구자가 제안한 교차검증의 주 지표 `mismatch_arousal`이 바로 이 축에 의존한다는 것이다.
>
> **해소책 — 채점 전에 주 지표를 교체한다** (채점 전이므로 과적합 아님):
> ```
> mismatch_query(쿼리, 곡) = | intensity_pct(곡) - intensity_target(쿼리) |
> ```
> `intensity_target`은 §3에서 LLM이 뽑아 `out/query_acoustic_targets.csv`에 이미 저장된 값이고,
> `intensity_pct`는 §1a에서 검증된 축이다. **불안정한 임베딩 축을 전혀 거치지 않으며**, 게다가
> 검색이 실제로 쓴 바로 그 양이라 해석이 더 직접적이다. `INTENSITY: NA`인 쿼리(T1-Q1, T2-Q2)는
> 이 검정에서 제외한다(4쿼리 잔존).
>
> - **주 지표**: `mismatch_query` ↔ 사람 점수 → **음의 상관** 예측 (사전 등록)
> - **보조 지표**: `mismatch_arousal` ↔ 사람 점수 → 같은 예측이나 **축 불안정으로 참고용**
> - `mismatch_valence_weak`는 §1b(검증된 valence 축 부재)에 더해 이제 이중으로 약하다 — 참고용.

### 9g. 산출물

| 파일 | 내용 |
|---|---|
| `06_lyrics_acoustic_assoc.py` | A1~A4 구현 |
| `out/lyrics_emotion_axes.csv` | `tag, lyr_valence, lyr_arousal` + 각 백분위 |
| `out/assoc_correlations.csv` | A1: `axis, feature, spearman_rho, pearson_r, p, q_fdr, n, passes_threshold` |
| `out/assoc_category_contrast.csv` | A2: `keyword, n, feature, cohens_d, mwu_p, q_fdr, passes_threshold` |
| `out/assoc_ceiling.csv` | A3: `target, r2_kfold, r2_groupkfold, gap` |
| `out/lyrics_acoustic_alignment.csv` | A4: `tag, lyr_valence_pct, lyr_arousal_pct, intensity_pct, brightness_pct, mismatch_arousal, mismatch_valence_weak` |
| `fig/assoc_heatmap.png` | A1 상관 히트맵(감성 축 × 음향 변수), 효과크기 하한 미달 셀은 회색 처리 |

### 9h. 알려진 한계

- `desc`는 **LLM이 가사에서 생성한 것**이라 가사 감성의 노이즈 섞인 측정치다. 게다가 13건은
  한자 혼입 버그가 있다(`report/01` §부수 발견). 임베딩에 미치는 영향은 미미할 것으로 보나 기록한다.
- 앵커 단어 선택(§9b)은 연구자 직관이며 사전 검증되지 않았다. 앵커를 바꾸면 축이 흔들릴 수 있다 →
  **민감도 확인**: 앵커에서 단어를 하나씩 빼며(leave-one-out) 축이 얼마나 안정적인지
  (`lyr_valence`의 LOO 변형 간 상관) 보고할 것. 상관이 0.9 미만이면 축을 신뢰하지 말 것.
- 상관은 인과가 아니다. A4의 교차검증도 관찰적이며, "불일치가 불만족을 낳는다"를 **입증하지 않는다**.
