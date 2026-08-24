> **이관 메모**: 원래 `main`의 `docs/WIP_multistage-stage-params-plan.md`. 레포 오너
> 결정(2026-08-24)으로 `main`의 `docs/`는 구조·설계 문서만 남기기로 해, 문서 자체가
> 이미 2026-08-08 종결(구현 안 함)로 스스로 마감한 이 계획 문서를 이관. 원본은 PR로
> `main`에서 삭제. 원문 내용은 그대로 유지.

> **⚠️ 2026-08-08 종결(구현 안 함)**: 이 문서가 전제로 삼은 조건("단일응답 stage_params로
> 부족하면 multistage로 전환")이 발생하지 않았다 — `epic/improved-playlist-maker`(PR #62)의
> 4단계 청취 비교에서 단일응답 어댑터(`groq_adapter.py`)에 `stage_minutes`·stage_params 6종·
> 가사 감상 임베딩 매칭·스테이지별 밴드 고정까지 반영한 결과가 청취상 충분해, multistage로
> 갈아탈 필요 자체가 없어졌다. 이 문서의 차용 방안은 미구현 상태로 보류하며, 짝이었던
> PR #61("2회차 요청 파라미터 재계산 스킵")도 같은 이유로 닫았다. 향후 multistage 채택이
> 다시 논의되면 이 문서를 참고 자료로 재검토할 것 — 지금은 실행 계획으로 취급하지 말 것.

# WIP: multistage 노드 구조를 AI 모드 stage_params에 차용하는 계획 (임시 문서)

**목적**: AI 모드 실측(2026-08-03, `epic/improved-playlist-maker` 브랜치)에서 발견된
과소적합(under-fitting) 문제 두 가지의 원인을 분석하고, `groq_multistage_adapter.py`의
순차 노드 구조를 3단계(stage_params) 스키마에 맞게 차용하는 방안을 정리한다. **이 문서는
계획만 담으며, 아직 구현하지 않았다.** 착수 시 이 문서를 갱신하고, 완료 후 삭제하거나
`docs/architecture.md`로 흡수한다.

**착수 순서(오너 결정, 2026-08-03, `docs/WIP_epic-improved-playlist-maker.md` 3.5) 참고)**:
이 문서의 multistage 차용은 **지금 바로 착수하지 않는다.** 먼저 아래 "도메인 변경" 절의
`stage_minutes` 신설만 단일응답 어댑터(`groq_adapter.py`)에 적용해 청취 테스트를 진행하고,
그 결과가 여전히 부족할 때만 이 문서의 나머지(순차 노드 구조 차용)로 넘어가 **단일응답
어댑터를 multistage로 교체(대체 구현 — 병행이 아님)**한다.

## 관찰된 문제 (재현 프롬프트)

> "60분동안 점점 숨차는 운동에 어울리는 노래로 해줘. 마지막 5분은 릴랙스하게."

실제 결과: 4구간 모두 균등하게 15분씩 배정되었고(마지막 5분 릴랙스 요청 무시),
energy·valence를 포함한 stage_params도 요청 의도(점점 고조 → 급격히 이완)를 뚜렷이
반영하지 못함.

## 원인 분석 — 서로 다른 두 문제

### 문제 A: 구간 길이(분) 자체가 애초에 LLM→도메인 경로에 없다 (아키텍처 갭)

`domain/models.py`의 `MoodParameters`에는 **구간별 길이(분) 필드가 없다.**
`domain/selection.py`의 `_stage_targets_and_counts()`(L223)는 `stage_energies`가 있어도
곡 **개수**만 `distribute_counts()`(L239, `domain/energy.py:32`)로 단계에 배분하며, 이
함수는 `total // stage_count`로 **거의 균등 분배**한다(나머지만 앞 단계부터 +1). 즉:

- LLM이 "마지막 구간은 5분만"이라고 완벽하게 말해도, **현재 스키마에는 이를 담을 필드
  자체가 없어서** 도메인에 절대 전달되지 않는다.
- 이건 프롬프트를 아무리 잘 써도 고쳐지지 않는 문제다 — **스키마 확장이 필요**.
- 참고로 `groq_multistage_adapter.py`는 2차 호출에서 이미 구간별 `길이(분)`을 받아오지만
  (`_stage2_stages()`, L233), 정작 최종 결과 조립(`interpret()`, L367)에서는 그 값을
  버리고 `target_minutes`(1차 값)만 쓴다 — 파일 docstring(L22-24)에 "도메인이 구간별
  개별 길이를 지원하지 않고 stage_count로 균등분배하기 때문"이라고 이미 명시돼 있었다.
  즉 이 문제는 3단계 신규 버그가 아니라 **원래부터 있던 도메인 제약**이며, multistage
  실험 때도 우회하지 못하고 알려진 제약으로 남겨뒀던 것.
- 커스텀 모드는 `StageSpec.song_count`로 이미 비균등 배분을 지원한다(`_stage_targets_and_counts`
  L230-233, `_field()` 우선순위) — AI 모드만 이 경로가 없는 상태.

### 문제 B: stage_params(energy·valence 등 7개) 값 자체의 소극적 안주

[[feedback-...]]는 아니지만 오늘 세션에서 이미 1차 조치(커밋 `4eb143f`)를 했다 —
`[지표 분포 통계]`(전체/밴드별 min/max/mean/median/std)를 시스템 프롬프트에 주입해
"조용한 발라드" vs "Roselia 격렬" 대조 실험에서는 값이 뚜렷이 갈리는 것까지 확인했다.
그런데도 이번 재현 프롬프트("점점 숨차는 운동")처럼 **한 번의 거대한 JSON 응답 안에서
brightness·start/end_energy·stage_count·stage_params(N×7개 실수)·tags·summary 등 십수 개
필드를 동시에 채우게 하면**, 모델이 각 필드에 쏟는 "주의"가 분산되어 개별 값이 다시
평이해지는 경향이 남아있다(관찰).

`groq_multistage_adapter.py`의 3차(`_stage3_energies`, L272)는 이미 **energy 하나만**
좁게 묻는 구조라 상대적으로 잘 분화된 값을 낸다 — 단일 대형 JSON 호출보다 **좁고 단일
목적인 순차 호출**이 값을 더 결정력 있게 뽑아내는 경향이 있다는 것이 이 프로젝트의 기존
경험적 근거(파일 상단 docstring: "각 파라미터를 순서대로 LLM에 물어 JSON을 조립").

## 차용 방안 — 순차 노드 재설계 (초안, 미확정)

`groq_multistage_adapter.py`의 4단계 골격을 아래처럼 확장한다(신규 어댑터 파일로 만들지,
기존 파일을 확장할지는 **미결정** — "열린 질문" 참고):

| 노드 | 현재(multistage) | 확장안 |
|---|---|---|
| 1차 | 전체 재생시간(분) | 그대로 재사용 |
| 2차 | 구간 수 + 구간별 (길이(분), 감정 키워드) | 그대로 재사용 — **단, 이번엔 길이(분)을 버리지 않고 신규 필드로 도메인까지 전달**(아래 "도메인 변경" 참고) |
| 3차 | 구간별 에너지 1개 값 | **구간별 7개 값**(energy, valence, lufs_integrated, lra, danceability_norm, instr_stem_ratio, speech_median)을 한 줄에 CSV처럼("energy,valence,lufs,lra,dance,instr,speech") — 2차와 같은 줄 단위 파싱 패턴 재사용. `[지표 분포 통계]`(오늘 추가한 `feature_stats`)를 이 노드의 user 메시지에 붙여 재사용(이미 계산 로직 있음, `routes._feature_stats()`) |
| 4차 | 요약 문장 | 그대로 재사용 |
| — | brightness는 미사용(0.0 고정) | **LLM 호출 없이 결정론적으로 파생**: 구간별 valence 평균을 -1~1로 재매핑. 별도 호출 비용 없음 |
| — | tags = 2차 감정 키워드 재사용 | 그대로 재사용 |
| — | song_type/same_as_previous 미지원 | 그대로 스코프 밖(기존 multistage와 동일한 알려진 제약 유지) |

**3차를 왜 5호출로 쪼개지 않고 7개 묶음 한 줄로 하는가**: 매 구간마다 LLM 호출 5번(7개
필드를 값끼리 다시 나누면)은 2~5구간 기준 최대 25회 호출이 되어 무료/저비용 모델
레이트리밋·지연 부담이 커진다. "구간당 1줄, 줄 안에 7개 숫자"는 2차의 "길이,키워드"
패턴과 동일한 절충(호출 수는 늘리지 않되 각 호출의 목적은 여전히 좁게 유지 — 구간별
음향 프로파일이라는 단일 주제).

## 도메인 변경 (필요 — 문제 A 해결에 필수)

1. `MoodParameters`에 `stage_minutes: list[int] | None = None` 추가(길이 = stage_count).
2. `_stage_targets_and_counts()`에 분기 추가: `stage_specs`(최우선) → `stage_minutes`가
   있으면 분(길이) 비율대로 곡 수 배분 → 없으면 기존 `stage_energies`/균등 분배로 폴백.
   (곡 수 비례 배분 자체는 `distribute_counts`를 분→초 비율 가중치로 일반화하면 재사용 가능.)
3. 커스텀 모드처럼 구간 최소 길이 하한 필요(`app.js`의 `MIN_WIDTH_MIN = 3`과 동일 기준으로
   서버 측도 클램프 — 지금 커스텀 모드는 프론트에서만 강제하고 서버는 무방비).
4. `stage_params`(현재 3단계 스키마, `selection.py:337` `_field()`)는 이미 존재하므로 3차
   결과를 `MoodParameters.stage_params`에 채우기만 하면 됨(추가 도메인 변경 불필요 — 이미
   AI 단일응답 경로가 이 필드를 소비하도록 3단계에서 배관됨).

## 열린 질문 (미결정 — 착수 전 확인 필요)

- **신규 어댑터 파일 vs 기존 확장**: `groq_multistage_adapter.py`를 직접 확장할지,
  `groq_multistage2_adapter.py`(가칭)로 분리할지. 기존 파일은 "실험용/파일럿"으로 명시돼
  있고 `MOOD_INTERPRETER=groq_multistage`로만 활성화되는 로컬 전용 옵트인 상태
  ([[decision-enable-groq-multistage-pending-review]] 참고, Render 미배포) — 분리하면
  기존 실험을 안 건드리고 새 실험을 병행할 수 있음.
- **호출 수 증가에 따른 지연**: 4회 순차 호출(1~4차)은 이미 기존 multistage의 비용이며,
  3차가 조금 더 커질 뿐 호출 횟수는 안 늘어남 — 그래도 순차 호출 자체의 레이턴시(4번
  왕복)가 단일 JSON 호출보다 훨씬 크다는 기존 트레이드오프는 그대로 남음. Render 콜드스타트
  + 4회 순차 호출이면 사용자 체감 대기시간이 상당히 늘 수 있어, 프로덕션 채택 여부는
  별도 판단 필요(PRD §9 열린 질문: 요청 큐잉 도입 시점과도 연결됨).
- **3차 파싱 실패 시 부분 성공 처리**: 구간별 7개 값 중 일부 줄만 파싱 실패하면 전체
  재시도(`_call_with_stage_retry`)할지, 실패한 구간만 `stage_params[i]=None`(도메인의
  기존 폴백 경로, `selection.py`가 None을 허용)으로 둘지 미결정.
- **brightness 파생 공식**: "구간별 valence 평균 → -1~1"의 정확한 매핑식(단순
  `2*mean(valence)-1`으로 충분한지, 가중 평균(구간 길이 가중)이 나을지)은 미정.
- **A/B 비교 대상**: 이 방안이 완성되면 기존 단일응답(`groq_adapter.py`, 오늘 `feature_stats`
  주입한 버전)과 실측 대조가 필요 — 어느 쪽이 실제로 의도를 더 잘 반영하는지는 아직
  가설일 뿐 검증 전.

## 관련 파일

- `src/backend/app/adapters/groq_multistage_adapter.py` — 차용 대상 노드 구조.
- `src/backend/app/adapters/prompt.py` — 현재 단일응답 시스템 프롬프트·`feature_stats` 포맷.
- `src/backend/app/domain/selection.py:223` `_stage_targets_and_counts()` — 도메인 변경 지점.
- `src/backend/app/domain/models.py` `MoodParameters` — `stage_minutes` 필드 추가 지점.
- `src/backend/app/domain/energy.py:32` `distribute_counts()` — 비율 배분 일반화 지점.
- `src/frontend/app.js:295` `MIN_WIDTH_MIN` — 서버 측 클램프 시 참고할 기존 프론트 기준값.

(2026-08-03 작성, 실측 재현 프롬프트 기반 원인 분석 완료. 구현 미착수.)
