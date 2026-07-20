# 음향 지표 감사 (acoustic feature audit) — Phase 2 착수 전 사전 점검

> 상태: 완료. Phase 2(`src/method-2`) 설계의 근거 문서.
> 계기: Phase 1(`01-lyrics_vector-searching.md`) 결론이 "다음은 음향 특성 결합"이었고,
> 그 착수 직전 "결합할 지표가 실제로 믿을 만한가"를 확인하려다 나온 결과.
> 데이터: `data/ground_truth_labels.csv` (사람이 붙인 정답 라벨 65행), `data/songs_master.csv` (661곡).

## 한 줄 결론

**`songs_master.csv`의 `energy`는 아무 신호가 없고 `energy_proxy`는 부호가 뒤집혀 있다.
`energy_full`이 유효한 강도 지표다. `mode_score`는 유효하지만 장/단조 축일 뿐 감정가(valence)가
아니며, 현재 데이터셋에는 검증된 valence 축이 존재하지 않는다.**

프로덕션 버그는 아니다 — 앱은 이미 알고 우회하고 있다(§3). 그러나 이 사실을 모르고 Phase 2를
시작했다면 깨진 컬럼 위에 실험을 쌓아 **"음향 결합은 효과 없음"이라는 거짓 기각**에 도달했을 것이다.

## 1. 방법

저장소에 이미 존재하던 `data/ground_truth_labels.csv`를 사용했다. 사람이 곡에 직접 붙인 라벨이며
3개 차원으로 구성된다:

| 차원 | 라벨 (곡 수) |
|---|---|
| `intensity` | loud (22), quiet (14) |
| `brightness` | bright (8), dark (8) |
| `party` | party (8), calm (5) |

각 후보 지표에 대해 **라벨 그룹별 평균**을 냈다. 지표가 유효하다면 loud > quiet, party > calm,
bright > dark 순서가 나와야 한다. 이 검증의 강점은 `intensity`와 `party`가 **서로 독립적으로 수집된
두 개의 라벨 세트**라는 점이다 — 둘이 같은 결론을 주면 우연으로 보기 어렵다.

## 2. 결과

### 2a. 강도(intensity) 계열 — `energy` 무효, `energy_proxy` 역전

| 지표 | loud (22) | quiet (14) | party (8) | calm (5) | 판정 |
|---|---|---|---|---|---|
| `energy` | 0.446 | 0.450 | 0.369 | 0.417 | **신호 없음** |
| `energy_proxy` | **−0.590** | **+0.336** | **−0.657** | **+1.399** | **부호 역전** |
| `energy_full` | **0.695** | **0.174** | **0.847** | **0.136** | **유효** |
| `i_mean` | 0.377 | −0.129 | 0.547 | −0.297 | 유효 |

두 독립 라벨 세트가 완전히 일치한다. `energy`는 두 차원 모두에서 구분에 실패했고(오히려 미세하게
역방향), `energy_proxy`는 두 차원 모두에서 **크게 뒤집혔다**.

컬럼 간 상관도 이를 뒷받침한다 — `energy` vs `energy_full` = **−0.436**, `energy_proxy` vs
`energy_full` = **−0.229**. 반면 `energy_full`은 실측 강도 시계열과 자연스럽게 붙는다
(`i_mean` +0.634, `i_max` +0.609).

곡 단위로 보면 더 분명하다:

| 곡 | `energy` | `energy_full` | 실제 |
|---|---|---|---|
| `poppin_party__375` **Yes! BanG_Dream!** | **0.079** | **0.900** | 프랜차이즈 대표 업템포 앤섬 |
| `poppin_party__465` 幾億光年 (Cover) | **0.910** | **0.140** | 95.7 BPM 어쿠스틱 발라드 |

`energy`는 이 두 곡의 순위를 **정확히 거꾸로** 매긴다.

**부수 관찰**: 원시 `rms_mean`은 loud 0.168 / quiet 0.174로 **구분에 실패**한다. 상용 마스터링이
음량을 평준화하기 때문으로 보이며, 따라서 "에너지"는 단순 음량이 아니라 `energy_full`처럼
밀도·동적 특성을 반영한 복합 구성이어야 한다는 근거가 된다.

### 2b. `mode_score` — 유효하지만 valence가 아니다

| 지표 | bright (8) | dark (8) | 판정 |
|---|---|---|---|
| `mode_score` | **+0.352** | **−0.286** | 유효 |

라벨 분리는 깨끗하다. 그런데 Phase 1의 사용자 채점과 대조하면 어긋난다:

| 곡 | 쿼리 | 사용자 점수 | `mode_score` 백분위 |
|---|---|---|---|
| `poppin_party__375` Yes! BanG_Dream! | "날아갈 것처럼 신나는" | **10** | **0.04** |
| `hello_happy_world__111` | "행복한 노래" | **9** | **0.24** |
| `hello_happy_world__109` | "행복한 노래" | **10** | **0.39** |

가장 밝게 들리는 곡들이 `mode_score` 하위에 있다. 모순이 아니라 **정의의 문제**다 — `mode_score`는
화성적 **장/단조** 축이고, J-rock·애니송은 단조로 밝고 신나는 곡을 흔하게 쓴다. 라벨러가 "bright"라고
표시한 곡과 사용자가 "행복하다"고 느낀 곡이 서로 다른 개념이었던 것이다.

**따라서 현재 데이터셋에는 검증된 강도 축은 있으나, 검증된 valence(감정가) 축이 없다.**

## 3. 이것은 프로덕션 버그가 아니다

`src/backend/app/repo/song_repo.py`(main 브랜치)의 docstring이 이미 명시하고 있다:

> `energy`(EMOI-MAP 펄스용)·`energy_proxy`·`acousticness_proxy`는 **발췌 구간만 반영 → 오판**.

즉 이 컬럼들은 곡 전체가 아니라 **발췌 구간**에서 계산된 레거시 값이고, 데이터팀이 2026-07-11
검증에서 이미 걸러냈다. 앱은 적재 시점(`load_songs()`)에 `energy_full`·`−acousticness_proxy`·
`i_min`·`i_mean`·`i_end`를 **power-mean(p=3) soft-OR**로 결합한 합성 강도를 따로 만들어
`Song.energy`로 쓴다. 이번 감사는 그 판단이 옳았음을 **독립적인 라벨 데이터로 재확인**한 셈이다.

위험은 앱이 아니라 **연구 쪽**에 있었다. `songs_master.csv`를 직접 읽는 파이프라인은 아무런 경고 없이
깨진 컬럼을 집어들게 된다. Phase 2는 이에 따라 앱의 합성 로직을 그대로 이식하기로 했다
(`method-2/DESIGN.md` §2).

## 4. 선행 연구 재해석 — `topic/mood_warmth`

`mood_warmth` 1라운드는 **"현재 선곡 파라미터(brightness=mode_score, energy)로는 지각의 대부분이
미설명"** 이라는 결론으로 끝났고, 그것이 MFCC 음색 탐색(`topic/mfcc_analysis`)으로 이어졌다.

그런데 그때 쓴 `energy`가 §2a에서 **무효로 판명된 바로 그 컬럼**이다. 그렇다면 그 null 결과는
"음향 특성이 감정을 설명하지 못한다"가 아니라 **"측정 도구가 고장나 있었다"** 로 재해석될 여지가 있다.

단, 과잉 해석은 경계한다. `mood_warmth`가 표적한 "가련/애절(pathos)"은 §2b가 지적한 **valence 축**에
가까운 개념이고, `energy_full`을 대신 넣는다고 자동으로 잡힌다는 보장은 없다. 이 재해석은
**가설이지 결론이 아니며**, Phase 2가 이를 부분적으로 가른다.

## 5. Phase 2에 미친 영향

이 감사 결과로 Phase 2 설계가 다음과 같이 바뀌었다:

1. **지표 화이트리스트 확정** — `energy`·`energy_proxy` 사용 금지. `energy_full` 기반 앱 합성
   로직을 이식(`DESIGN.md` §2).
2. **`BRIGHTNESS` 축에 "무관(NA)" 옵션 도입** — LLM이 "행복 → BRIGHTNESS 1.0"으로 단순 매핑하면
   §2b의 함정에 그대로 빠진다. 프롬프트에 장/단조 축임을 명시하고 NA를 허용했다.
3. **축을 3개로 제한** — 검증된 것만(intensity, brightness, tempo). 쿼리 6개로는 아무것도
   적합시킬 수 없으므로 축을 늘리는 건 과적합일 뿐이다.
4. **valence 부재를 사전 선언된 한계로 기록** — "슬픈 노래"가 Phase 2에서도 실패하면 원인은
   결합 방식이 아니라 **feature 공간의 공백**일 가능성이 높다. 그 경우 후속은 `mood_warmth`의
   발성 지표(f0_range_st·HNR·shimmer·합성 c3)를 661곡으로 확장하는 것이며, 보컬 스템은
   Phase 1 ASR 준비 과정에서 이미 661곡 전부 확보돼 있어 재분리 비용이 없다.

## 6. 남는 권고

- **`songs_master.csv`에 경고를 남길 것**: 이 CSV를 직접 읽는 신규 파이프라인은 `energy`·
  `energy_proxy`·`acousticness_proxy`가 발췌 기반 레거시임을 알 방법이 없다. 현재 그 지식은
  `song_repo.py` docstring에만 있다. 데이터 사전(`docs/`)이나 CSV 헤더 주석으로 올리는 것을 권한다.
- **`ground_truth_labels.csv`는 저평가된 자산이다**: 65행뿐이지만 이번 감사에서 두 개의 독립 차원이
  일관된 결론을 줬다. 신규 음향 feature를 도입할 때 **표준 회귀 검증 세트**로 상시 사용할 것을 권한다.
  이번 감사는 15분이 걸렸고, 없었다면 Phase 2 전체(GPU 시간 + 연구자 청취 수십 곡)를 낭비할 뻔했다.

## 7. 한계

- 라벨 표본이 작다(brightness 16곡, party 13곡). 방향성 판정에는 충분하지만 효과 크기를
  정밀 추정할 수는 없다.
- 라벨러가 1인인지 다수인지 이 문서 작성 시점에 확인하지 못했다. 다수라면 라벨 간 일치도가
  추가 검증에 쓰일 수 있다.
- §2b의 "valence 축 부재"는 `mode_score` 하나만 검토한 결과다. `shape`·`camelot`·스펙트럼
  계열(`cen_mean` 등)이 valence를 잡을 가능성은 검토하지 않았다 — Phase 2 결과에 따라 후속 과제.
