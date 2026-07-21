# 3차 제어 다변수 확장 — 무드/가사 축 검토 (report/01 §5 후속)

**세션일**: 2026-07-21. `report/01` §5("다음 단계, 아이디어 수준, 미착수")가 남긴 mood·가사
축 확장 아이디어를 이번 세션에서 처음으로 실제 검토했다. 설계 확정·구현은 아직 안 했고,
조사 결과와 구체적 설계 제안만 정리해 다음 세션(메인 기기)으로 넘긴다.

## 1. 배경 — 이번 세션이 어디서 시작했나

원래 목적은 무관한 작업(morfonica 곡의 조성 오검출 조사)이었는데, 그 과정에서 나온 발견들이
`report/01` §5가 미리 우려했던 지점("mood·drama는 자체 산출 필요, 가사는... '가사와 음향은
거의 직교' 결과와 상충 여부 확인 필요")과 정확히 맞물려서 자연스럽게 이 주제로 이어졌다.
관련 세부 조사·수정 내역은 `topic/audio_feats_analysis/report/06`에 있고, 이 문서는 그
결과를 §5의 "다음 단계" 관점에서 재정리한 것이다.

## 2. 이번 세션에서 확인한 사실

### 2a. `key`(조성) 라벨 버그 발견·수정 — 세부는 `audio_feats_analysis/report/06`
`KS_PROFILES` 생성 시 `np.roll` 부호가 반대라 조성 라벨이 결정론적으로 어긋나는 버그를
찾아 수정 완료(`topic/audio_feats_analysis/src/method-1/config.py`). 661곡 전체 재산출은
원본 오디오가 이 기기에 없어 메인 기기로 인계됨(`audio_feats_analysis/report/06` §7).

### 2b. 전체 피쳐 신뢰도 재점검 — 세부는 같은 문서 §5
`energy`/`energy_proxy`/`acousticness_proxy`/`instrumentalness_proxy`(레거시, 발췌 기반)와
`key`/`est_key`(위 버그)만 실제로 깨져 있었고, `mfcc_*`·`contrast`·`mode_score`·
`energy_full`·대부분의 `tempo` 사용처는 이미 검증된 범위 안에서 유효하다. 즉 3차 제어
확장에 쓸 수 있는 재료 자체는 많다 — 문제는 "재료가 없다"가 아니라 "무드·가사처럼 아직
검증된 축이 없는 영역"에 있다.

### 2c. `brightness` 축은 이미 만들어져 있었다 (단, multistage엔 없음)
단일호출 어댑터 `groq_adapter.py`엔 `brightness`(-1~1) 파라미터가 있고,
`domain/selection_stage_c.py`의 `_brightness_scores()`가 `mode_score` min-max 정규화(주) +
`shape` 보조가중으로 이미 구현돼 있다. 그런데 `groq_multistage_adapter.py`(현재
실사용 중인 3~4단계 순차 호출 어댑터)는 **의도적으로 이 질문을 빼고 `brightness=0.0`
고정**이다(어댑터 docstring: "이 파이프라인엔 밝기 축 질문이 없다"). 즉 재사용 가능한
뼈대는 있지만 지금 실사용 흐름엔 연결이 안 돼 있다.

**주의**: 이 뼈대를 그대로 재연결하면 안 된다. `mode_score`는 `vector_embedding/report/02`
§2b가 이미 확인했듯 "장/단조" 축이지 이 장르(J-rock/애니송)에서 검증된 밝기(valence)가
아니다("가장 밝게 들리는 곡들이 mode_score 하위에 있다"). LLM은 사용자의 "밝고 기분 좋은"
요청을 이 축에 매핑하게 될 텐데, 그 매핑 자체가 이미 알려진 결함이다.

### 2d. "가사와 음향은 거의 직교" — report/01 §5의 우려가 정량적으로 이미 확정돼 있었다
`vector_embedding/report/03`(n=661, 관찰연구)의 한 줄 결론: **가사 감정과 실제 음향
강도는 통계적으로 탐지되나 실용적으로 무의미한 수준으로만 연관되고, 밴드를 넘어서는
예측력은 사실상 0**. 가사가 슬픈 곡(108) vs 행복한 곡(58) 비교에서 `intensity`(검증된
강도 축) 차이는 d=−0.14(유의하지 않음) — 실제 청감으로는 구분이 안 된다. 이게 Phase 1의
"슬픈 노래 틀어줘" 쿼리가 가사 임베딩 검색에서 0.3/10을 받은 이유를 정확히 설명한다
(가사만 슬프고 소리는 안 슬픈 곡을 자신 있게 추천).

**함의**: 가사 임베딩을 3차 제어(혹은 별도 축)에 넣더라도, **가사 신호가 검증된 음향 제약
(에너지 등)을 뒤집을 수 있는 구조로 설계하면 안 된다.** 이미 `selection_stage_c.py`의
Stage C(`lyric_scores`)가 "가사로 후보 풀을 먼저 좁히고 → Stage A가 그 안에서 에너지로
하드 선택"하는 구조라 완전히 무방비는 아니지만, **가사가 먼저 풀을 좁히는 순서라서 원래
에너지 조건에 맞는 곡이 가사 단계에서 먼저 걸러질 위험**은 남아있다(§3 참조).

## 3. 이번 세션에서 나온 설계 제안 (미착수, 다음 세션에서 설계 확정 필요)

**핵심 아이디어**: Stage C(가사)와 Stage A(에너지)의 순서를 뒤집는다 — **에너지/무드/템포
하드 필터가 먼저 후보를 좁히고, 그 안에서 가사 임베딩 유사도를 소프트 정렬 기준으로
쓴다.** §2d의 직교성 문제를 구조적으로 회피하는 방향 — 가사가 아무리 안 맞아도 최종 후보는
항상 에너지 조건을 만족한 곡들 중에서만 나온다.

구현 시 짚어야 할 것 (설계 미확정):

1. **삽입 위치**: Stage A는 이미 `window[:count]`로 최종 곡을 확정하므로, 가사 유사도는
   별도 후속 단계가 아니라 **`window.sort(...)`(현재 밝기 버킷 거리로 정렬하는 지점)에
   세 번째 축으로 끼워 넣어야 한다.** 밝기·가사유사도 두 소프트 신호의 우선순위/가중치
   결합 방식은 미정.
2. **허용창 내 후보 수 확인 필요**: `_TOL=0.08` 에너지 허용창 + 밴드 필터가 겹치면 후보가
   한 자릿수로 줄어드는 경우가 흔할 수 있음 — 이 경우 가사 정렬은 사실상 무의미해진다.
   실측(허용창 내 후보 수 분포)이 먼저 필요.
3. **가사 임베딩 커버리지 확인 필요**: 로컬 전사(`work/transcripts/`)는 14곡뿐이었다
   (`vector_embedding/src/method-1`, gitignore 대상이라 기기마다 다를 수 있음). 실제
   커밋된 `out/embeddings.npz`가 몇 곡을 커버하는지, eligible_band 전체(661곡 중 다수)에
   못 미치면 미커버 곡의 처리 방침(중립값? 정렬에서 제외?)도 정해야 한다.
4. **유사도 쿼리 텍스트 선택**: 2차 단계에서 나오는 구간별 감정 키워드는 "잔잔한" 같은
   단어 하나뿐이라 임베딩 신호가 약할 수 있다. 사용자 원문 요청 전체를 쿼리로 쓰는 편이
   임베딩 품질상 유리할 가능성이 높음 — 실측 비교 필요.

## 4. mood(brightness) 축 재도입에 대한 권고

`mode_score`를 그대로 재연결하지 말 것(§2c). 두 가지 대안:
- **(a) 기존 검증된 축 재검토**: `energy_full`·`contrast`·`mfcc_*` 조합으로 이미 검증된
  다른 축이 "밝기"에 더 가까운지 재검토.
- **(b) PCA 등으로 새 합성축 탐색 + 반드시 ground-truth 재검증**: PCA는 "데이터에 어떤
  축이 있는지"만 찾아줄 뿐 "그 축이 사람이 느끼는 밝기와 일치하는지"는 보장 안 한다.
  `data/ground_truth_labels.csv`(65행, 손라벨)로 방향성 재검증 없이 그대로 LLM
  파라미터에 연결하면 "brightness v2"라는 이름으로 같은 결함을 재도입하는 셈이 된다.

## 5. 다음 세션 인수인계 (메인 기기에서 할 것)

1. `audio_feats_analysis/report/06` §7의 661곡 재산출(`key` 버그 수정 반영)부터 처리.
2. `out/embeddings.npz` 커버리지 확인(§3-3) — 661곡 중 몇 곡, 어느 밴드가 비어있는지.
3. `_TOL=0.08` 에너지 허용창 내 후보 수 분포 실측(§3-2) — 가사 정렬이 실제로 유의미한
   표본 크기를 가질지 사전 확인.
4. Stage C→A 순서 반전 설계 확정(§3-1) — 밝기·가사유사도 결합 방식 결정 후
   `selection_stage_c.py` 반영.
5. mood(brightness) 축은 §4의 (a)/(b) 중 하나를 먼저 검증하고 나서 3차 제어에 연결 —
   `mode_score` 직결 금지.
6. tempo는 이미 `final_bpm`(bestdori 우선)이 충분히 검증돼 있어 3차 제어 확장에 바로
   써도 무방(추가 검증 불필요, `audio_feats_analysis/report/05`, `02` 참조).

## 6. 레퍼런스
- `../backgroud.md`, `../live-architecture.md`, `01-multistage_param_control_pilot.md`
  (이 문서가 이어받는 원 배경·§5 아이디어)
- `topic/audio_feats_analysis/report/06-key-profile-roll-bug.md`(key 버그, 전체 피쳐
  신뢰도 표)
- `topic/vector_embedding/report/02-acoustic_feature_audit.md`(`mode_score` 스코프 한계)
- `topic/vector_embedding/report/03-lyrics_acoustic_association.md`(가사-음향 직교성,
  n=661 정량 근거)
- `topic/vector_embedding/report/01-lyrics_vector-searching.md`(Phase 1 "슬픈 노래" 0.3/10
  실패 사례)
- `topic/selection_pipeline/prod_snapshot/domain/selection_stage_c.py`(Stage A/B/C 현재
  구현, `_brightness_scores()`, `lyric_scores` 파라미터)
- `src/backend/app/adapters/groq_multistage_adapter.py`(`main` 브랜치, 현재 실사용 3~4단계
  어댑터)
