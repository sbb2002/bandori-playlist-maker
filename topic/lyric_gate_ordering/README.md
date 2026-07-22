# 가사 후보추림 순서 재검증 (topic/lyric_gate_ordering)

## 배경

`mood_axis_topdown`에서 GEMS-9 탑다운 검증을 진행하던 중(n=1 파일럿·n=1 라운드2 모두
`wonder`/`transcendence`/`power`/`sadness` 4항목 미통과, `report/01`·`report/02`), 사용자가
"n≥20 확대까지 실패하면 마지막 대안이 뭐냐"고 물었다. 답으로 나온 게 **가사 기반 후보추림을
현재 파이프라인 순서배정 로직 앞에 두는 방식**이었는데, 조사해보니 이건 완전히 새 아이디어가
아니라 `selection_pipeline`에서 v1~v3 세 라운드에 걸쳐 **이미 실제로 구현하고 실행까지 한**
방법론이었다(설계만 해두고 안 해본 게 아님). 그런데:

1. v3(실제 프로덕션 `build_setlist()` 코드로 검증한 라운드)의 관측 효과크기가 매우 작아서
   (dz=-0.116), 80% 검정력에 필요한 표본이 **쿼리 583개**로 나온다(`selection_pipeline/
   report/03` §1) — 기존에 언급되던 "82~85"는 v1(더 단순한 재현 버전, dz=0.313)의 사후
   재검정 수치라 v3와 기준이 다르다.
2. v3가 테스트한 순서는 **가사 유사도로 먼저 후보를 좁히고, 그 안에서 에너지(intensity)
   하드필터를 돌리는 것**(Stage C → Stage A)이었다. 그런데 `llm_param_control_separate/
   report/02`가 이 순서 자체를 문제로 지적했다 — 가사·음향이 거의 직교(`vector_embedding/
   report/03·04`)라서, 가사가 먼저 걸러버리면 원래 에너지 조건에 맞는 곡이 그 전에 이미
   빠져나갈 위험이 있다는 것. 그래서 **순서를 반전**(에너지 하드필터 먼저, 가사 유사도는 그
   안에서 소프트 정렬)하자는 설계가 나왔는데 **한 번도 실행된 적이 없다**.

이 폴더는 (a) 583 규모의 표본을 실제로 어떻게 확보할지, (b) v3와 같은 순서(가사 먼저)와
반전 순서(에너지 먼저) 중 어느 쪽이 더 나은지를 함께 검증한다. 사용자 판단: "어차피 지금은
다양하게 해보는 수밖에 없다" — 두 순서 다 시도한다.

## 이미 확인된 것 (기존 연구 인용, 재실행 금지)

| 항목 | 결과 | 근거 |
|---|---|---|
| Stage C(가사 먼저 → 에너지) v1 | 유의차 없음, 검정력 부족(관측 dz=0.313, 필요 쿼리 82~85) | `selection_pipeline/report/01`, `note/stat_arm1vs2.md` |
| Stage C(가사 먼저 → 에너지) v2 | 보류(단순재현) | `selection_pipeline/DESIGN_v2.md` |
| Stage C(가사 먼저 → 에너지) v3 | 실코드 검증, 유의차 없음(p=0.558), 관측 dz=-0.116(오히려 역방향), 필요 쿼리 **583** | `selection_pipeline/report/03`, `DESIGN_v3.md` |
| 가사 임베딩 단독(valence) | 4.67/10, 채택기준(≥7.0) 미달 | `vector_embedding/report/04` |
| 가사+음향 late-fusion(α=0.5) | 2.89(가사단독보다 악화), `acou_match` ρ=-0.588(역상관) | `vector_embedding/report/04` |
| Stage C→A 순서반전(에너지 먼저 → 가사 소프트정렬) | **설계만 있고 미실행** | `llm_param_control_separate/report/02` |
| intensity(에너지) 단독 | 독립적으로 유효, ρ=-0.382 p=0.037 | `vector_embedding/report/04` A4 |

## 이 폴더의 목표

1. **표본 확보 방법 설계**: 583(또는 현실적으로 조정한 목표)개 쿼리를 실제로 만들고 평가할
   방법 — 쿼리 자동 생성(LLM 활용 가능성), 평가자 확보(사용자 1인 반복 vs 외부 평가자),
   평가 방식(블라인드 Likert, 기존과 동일)을 정한다.
2. **두 순서 비교**: 기존 프로덕션(baseline, 가사 미사용) vs Method A(가사 먼저 → 에너지,
   v3와 동일 구현 재사용) vs Method B(에너지 먼저 → 가사 소프트정렬, 신규 구현) 3-arm 비교.
3. **사전 검정력 계산**: v3의 관측 효과크기(dz=-0.116)를 하한으로 잡되, Method B는 아직
   관측치가 없으므로 최소 유의미 효과크기(예: dz=0.3, 중간 효과)를 가정해 별도 계산한다 —
   과거처럼 "일단 24개 돌리고 사후에 부족했다고 확인"하는 순서를 반복하지 않는다
   (`framework.md`류 문서들이 공통으로 강조하는 원칙).

## 폴더 구조

표준 구조(`src/`, `fig/`, `report/`, `ref/`, 루트 `README.md`)를 따른다. `selection_pipeline/
prod_snapshot/`의 기존 벤더링 코드(`build_setlist()`, `build_setlist_with_stage_c()`)를
재사용하고, Method B(순서 반전)만 신규 구현한다 — 이미 검증된 로직을 새로 짜지 않는다.

## 다음 단계

표본 확보 방법(쿼리 생성·평가자·목표 표본 크기)에 대한 사용자 결정이 먼저 필요하다 —
설계를 더 진행하기 전에 확인.

## 실행 방법

### 쿼리 자동 생성

```bash
python 01_generate_queries.py
```

이 스크립트는:
- Groq LLM으로 4개 카테고리(밴드지정, 강도/밝기, 상황/기능성, 진행형 아크)별로 150개씩 총 600개 쿼리 생성
- 진행상황을 `out/generation_progress.json`에 캐싱 (중단 후 재실행 시 이전까지의 결과 유지)
- 중복 제거 후 결과를 `out/generated_queries.csv`로 저장

**필수 준비:**
- `work/groq.key` 파일에 Groq API 키가 있거나, 환경변수 `GROQ_API_KEY` 설정

**완료 후:**
- `out/generated_queries.csv` 열기
- `keep` 컬럼을 검토하면서 TRUE/FALSE로 필터링 (또는 불필요한 행 삭제)
- 필터링된 결과물로 블라인드 평가 진행
