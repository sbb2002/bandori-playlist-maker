# GEMS-9 n=1 파일럿 — §3 후보 신호 전수 스크리닝 결과

> 상태: n=1(사용자 본인) 파일럿 완료. 통계적 확증이 아니라 **n≥20 확대 여부를 판단하기 위한
> 방향성 스크리닝**이다(`framework.md` §2e 표본 계획). 결론은 잠정적이다.

## 1. 방법

- 라벨: `out/gems9_pilot_candidates.csv` — 35곡, GEMS-9 9항목(wonder/transcendence/
  tenderness/nostalgia/peacefulness/power/joyful_activation/tension/sadness) 1~5점.
- 후보 신호: `framework.md` §3a 피쳐 신뢰도 등급을 그대로 적용.
  - **Tier 1**(신뢰): `mfcc_1~13_mean`, `contrast_mean`, `energy_full`, `rms_mean`, `bpm`
    (`topic/audio_feats_analysis/out/audio_feats.csv`, GEMS 35곡 전수 커버).
  - **Tier 2**(조건부): `mode_score`, `tempo_bpm` — 결과에 저신뢰 표시.
  - **Tier 3**(불신뢰): `key`/`camelot`/`energy`/`energy_proxy`/`acousticness_proxy`/
    `instrumentalness_proxy`/코드진행 파생값 — 스크리닝 자체에서 제외(§3a 규칙 그대로 적용).
  - **Vocal(참고)**: `jitter_local`/`shimmer_local`/`hnr_mean`/`f0_*`/`vocal_centroid`
    (`topic/mood_warmth/vocal_features_full.csv`) — GEMS 35곡과의 overlap이 **3곡뿐**이라
    통과 판정에서 항상 제외(`n < MIN_N=10`)하고 숫자만 참고용으로 남김.
- 통계: Spearman ρ, 축(GEMS 항목)마다 그 축에 돌린 신호 개수 기준 BH-FDR 보정.
- 통과 기준(§3c 그대로): `n ≥ 10` AND `|ρ| ≥ 0.4` AND `q_bh < 0.05`.
- 스크립트: `src/method-1/screen_candidate_signals.py` → `out/screening_results.csv`(234행,
  판정 전체).

## 2. ⚠️ 결과를 읽기 전에 — 항목 간 halo effect

스크리닝을 실행하기 전에 GEMS-9 9항목끼리 상관을 먼저 봤다. n=1 채점에서 항목 간 상관이
매우 높다:

|            | wonder | transc | tender | nostal | peace | power | joyful | tension | sadness |
|---|---|---|---|---|---|---|---|---|---|
| **wonder**      | 1.00 | **+0.94** | -0.48 | -0.27 | -0.55 | +0.68 | -0.25 | +0.58 | +0.46 |
| **tenderness**  | -0.48 | -0.41 | 1.00 | **+0.77** | **+0.88** | -0.26 | -0.23 | **-0.82** | -0.02 |
| **peacefulness**| -0.55 | -0.42 | **+0.88** | **+0.79** | 1.00 | -0.34 | -0.38 | **-0.88** | -0.01 |
| **joyful_activation** | -0.25 | -0.32 | -0.23 | -0.49 | -0.38 | -0.21 | 1.00 | +0.16 | **-0.72** |

(전체 9x9 행렬은 스크리닝 스크립트 실행 로그 참고.)

**해석**: 이 라운드에서 9항목은 실질적으로 독립 측정이 아니라 **2~3개 잠재축**으로 수렴한다 —
① `wonder`/`transcendence`(거의 동일 항목처럼 응답, ρ=0.94), ② `tenderness`/`nostalgia`/
`peacefulness` vs `tension`(강한 역상관 클러스터), ③ `joyful_activation` vs `sadness`(역상관).
`power`/`sadness`는 상대적으로 독립적. GEMS 이론의 3상위요인(Sublimity/Vitality/Unease)과
방향은 대체로 일치하지만, n=1이라 "9항목을 각각 독립적으로 채점했다"기보다 **채점자 한 명의
전반적 인상(밝음↔어두움, 격함↔평온함) 한두 축이 9개 항목에 새어나온 결과일 가능성이 높다.**

이 때문에 아래 §3의 "34건 통과"를 "9개 GEMS 항목이 각각 오디오 피쳐로 검증됨"으로 읽으면
**과대해석**이다. 정확히는 "이 채점자가 쓴 밝음/평온 축과 텐션/에너지 축 각각에 대해 오디오
피쳐 후보가 존재한다"는 더 좁은 결론이다.

## 3. 스크리닝 결과 요약

통과(34건)를 GEMS 항목별로 묶으면:

| GEMS 항목 | 통과 신호 수 | 대표 신호(|ρ| 최대) |
|---|---|---|
| peacefulness | 9 | `mfcc_11_mean` ρ=-0.755 |
| nostalgia | 8 | `contrast_mean` ρ=+0.708 |
| joyful_activation | 8 | `mfcc_1_mean` ρ=+0.664 |
| tension | 5 | `mfcc_13_mean` ρ=+0.727 |
| tenderness | 4 | `contrast_mean` ρ=+0.615 |
| wonder | 0 | — |
| transcendence | 0 | — |
| power | 0 | — |
| sadness | 0 | — |

`mode_score`(Tier 2)는 `tension`(ρ=-0.713), `tenderness`(+0.601), `peacefulness`(+0.598),
`nostalgia`(+0.465)에서 통과했다 — §1d에서 이미 "밝기이긴 하나 valence는 아니다"로 정리된
피쳐가, GEMS의 "평온/애상 vs 긴장" 축에는 오히려 잘 맞을 수 있다는 신호다(단 Tier 2라 단독
근거로는 약함, §3a 규칙).

`wonder`/`transcendence`/`power`/`sadness` 4항목은 Tier 1/2 어떤 신호로도 통과하지 못했다 —
§2 halo effect 표를 보면 `wonder`/`transcendence`는 서로 강하게 얽혀 있지만 오디오 피쳐와는
따로 놀고, `power`/`sadness`는 상대적으로 독립적인데도 신호가 안 잡힌다. 현재 후보 신호
집합으로는 이 4항목을 661곡 전체로 확장할 수 없다는 뜻(§2e 기준).

## 4. 다음 단계 판단 (framework.md §4a 기준)

- §3 기준으로 "GEMS-9 중 일부 항목(peacefulness/nostalgia/joyful_activation/tension/
  tenderness)이 통과"했으므로 시나리오 A(§4a-1, energy 하드필터를 GEMS 축으로 대체) 조건은
  형식적으로 충족한다.
- 그러나 §2의 halo effect 때문에, 이 통과를 **n≥20 확대 없이 그대로 시나리오 A에 연결하는
  것은 위험**하다 — 5개 "통과 항목"이 실제로는 1~2개 잠재축의 재탕일 수 있어서, 파이프라인에
  9개 항목을 별도 신호처럼 연결하면 `report/04`가 지적한 것과 유사한 중복/과최적화 위험이
  있다.
- **권고**: n≥20 확대 라운드(`gems9_google_form.gs`, §2e)로 넘어가 항목 간 halo effect가
  다인원 평균에서도 유지되는지 먼저 확인한 뒤, 유지되는 잠재축 단위(9항목이 아니라 2~3개
  합성축)로 시나리오 A를 설계하는 게 안전하다. 사용자 확인: **지금 당장 n≥20을 시작하지는
  않음** — 필요 시 별도로 요청.

## 산출물

- `src/method-1/screen_candidate_signals.py` — 스크리닝 스크립트(재실행 가능, 축마다 BH-FDR).
- `out/screening_results.csv` — 234행 전체 판정(통과/미통과 포함).
