# 무드 축 탑다운 검증 (topic/mood_axis_topdown)

## 배경

`audio_feats_analysis/report/10`(조성 검출 리서치 종결) §4가 마지막에 남긴 문제제기에서
시작한다: 지금까지의 접근은 "오디오 신호 → 조성/에너지 등을 최대한 정확히 추정 → 그걸로
무드를 설명"하는 **바텀업**이었는데, 조성 정확도를 아무리 끌어올려도 `mode_score`(장/단조
축) 자체가 "밝기(valence)"와 일치하지 않는다는 게 이미 확인돼 있어(§ 아래 표) 최종 목표
(감성언어 기반 선곡)에 비례해서 기여하지 않을 수 있다는 정황이 쌓여 있었다.

같은 세션(2026-07-22)에서 이 문제를 다시 짚었고, 지금까지 여러 트랙(`audio_feats_analysis`,
`vector_embedding`, `selection_pipeline`, `mood_warmth`, `llm_param_control_separate`)이 독립
적으로 시도한 결과를 취합해보니 공통점이 드러났다: **실패한 시도들은 전부 "신호를 먼저 만들고
나중에 검증"하는 순서**였고, 유일하게 깔끔히 작동한 방법론은 `vector_embedding/report/02`
(acoustic_feature_audit)의 순서 — **ground truth 라벨을 먼저 놓고 후보 신호를 체로 거르는
것**이었다. 이 폴더는 그 순서를 정식 프로세스로 승격시켜 "탑다운" 전환을 구체적인 방법론으로
설계한다.

## 목적

사용자가 실제로 쓸 감성 언어(밝다/어둡다/애절하다/신난다 등)에서 출발해, 그 언어가 가리키는
축을 먼저 정의하고, 그 축에 대해 이미 계산된 모든 후보 신호(오디오 feature·가사·보컬 발성 등)
를 ground truth 라벨과 대조해 **통과한 신호만** 3차 LLM 제어·선곡 파이프라인에 연결한다.
피쳐 공학(새 신호 개발)은 스크리닝을 통과하지 못한 축에 대해서만, 그것도 마지막 수단으로
투자한다.

상세 4단계 절차와 축별 현황 표는 [`framework.md`](framework.md) 참조.

## 왜 별도 폴더인가

이 작업은 특정 오디오 feature 하나를 검증하는 소규모 실험이 아니라, **여러 기존 주제 폴더의
결론을 가로질러 참조하며 앞으로의 모든 축 검증 작업이 따라야 할 상위 방법론**이다.
`audio_feats_analysis`(조성/템포), `vector_embedding`(가사 임베딩), `mood_warmth`(보컬 발성),
`llm_param_control_separate`(LLM 파라미터 설계) 중 어느 한 곳에 종속시키기보다 별도 폴더로
분리해, 이후 각 축의 스크리닝·ground truth 확장 작업이 여기 쌓이도록 한다.

## 지금까지 알려진 것 (기존 연구 취합)

| 후보 신호 | 대상 축 | 상태 | 근거 |
|---|---|---|---|
| `energy_full`(+ i_min/i_mean/i_end 합성) | intensity | **유효** | `vector_embedding/report/02` §2a |
| `energy`, `energy_proxy` | intensity | **무효/부호역전** — 사용 금지 | 위와 동일 |
| `mode_score`(장/단조) | valence(밝기) | 유효하지만 **valence 아님** | `vector_embedding/report/02` §2b |
| 가사 임베딩 단독 | valence(슬픔/기쁨) | 약함(4.67/10, 채택기준 미달) | `vector_embedding/report/04` |
| 가사+음향 late-fusion | valence | **실패**(가사 단독보다 악화, ρ=−0.588) | `vector_embedding/report/04` |
| 보컬 발성(jitter/shimmer/HNR/f0_range, 합성축 c3) | valence/pathos | **null로 종결**(2026-07-18, 재시도 비권장) | `mood_warmth/ROUND2-valence-proxy-DESIGN.md` |
| 코드진행 케이던스 재판별 | key(근접조 해소) | 실패(정답률 악화) | `audio_feats_analysis/report/08` |
| Stage C(가사 후보추림) 프로덕션 삽입 | 사용자 만족도 | 유의차 없음(검정력 부족, n↑ 필요) | `selection_pipeline/report/03` |

**결론적으로 지금 카탈로그에서 valence(슬픔↔기쁨) 축은 오디오·가사 양쪽에서 시도된 방법이
모두 막혀 있다.** 이 폴더의 1순위 질문은 "valence를 더 짜낼 방법을 찾는다"가 아니라
"valence 없이도 최종 목표에 기여할 수 있는 구조가 무엇인가"까지 포함해서 판단하는 것이다
(`framework.md` §4).

## 진행 상황

**§1(목표 어휘 확정) 완료(2026-07-22)** — 실질 축은 `intensity`(충분·검증됨)·`valence`·
`pathos`(둘 다 ground truth 확장 필요) 3개로 확정, `tempo`는 재검증 불필요, 상황/기능성·
진행형 아크 쿼리는 별도 축이 아니라 기존 축의 조합·궤적으로 처리하기로 사용자 확인
(`framework.md` §1d).

**§2(ground truth 확장) 중 청취 불필요한 부분까지 완료(2026-07-22)**:
- `party` 라벨이 `intensity`의 하위집합임을 확인 → 별도 축 승격 안 함(`framework.md` §2a).
- `valence`·`pathos` 청취 후보곡 CSV 준비 완료(§2d) — 청취·채점만 남음.

## 다음 세션 인수인계 (다른 로컬에서 이어하기)

**할 일**: 아래 두 CSV를 열어 청취하며 빈 칸을 채운다. 오디오 파일은 필요 없고 `url`
컬럼의 유튜브 링크로 들으면 된다.

1. `out/valence_candidates.csv`(33곡) — `valence_rating_1to10` 채점(0=매우 슬픔/처연,
   10=매우 밝음/기쁨).
2. `out/pathos_candidates.csv`(29곡) — `pathos_rating_0to10` 채점("애절하나 위로되는가",
   0=전혀 위로 안 됨, 10=애절하며 위로됨). `prior_*` 컬럼(예전 esora 유사도 채점)은 참고만
   하고 그대로 베끼지 않는다.

각 CSV의 컬럼 의미·생성 방법은 `src/method-1/README.md` 참조. 채점이 끝나면 §3(후보 신호
전수 스크리닝, `framework.md`)으로 이어간다 — 이 단계도 청취 불필요, 이미 계산된
`audio_feats.csv`·`mood_warmth/vocal_features*.csv` 등을 새 라벨과 대조만 하면 된다.

## 폴더 구조

표준 구조(`src/`, `fig/`, `report/`, `ref/`, `paper.md`, 루트 `README.md` 참조)를 따르되,
현재는 실행 전 단계라 `framework.md`(방법론 설계 문서)만 존재한다. 실행이 시작되면
`src/method-1/`(스크리닝 스크립트), `report/01-*.md`(스크리닝 결과)가 추가된다.
