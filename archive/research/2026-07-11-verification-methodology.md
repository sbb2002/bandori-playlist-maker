# 플레이리스트 품질 검증 방법론 + 현재 엔진 베이스라인

작성: R&D팀 팀장 (opus) · 2026-07-11
티켓: setlist-maker 플레이리스트 품질을 **객관적으로 반복 측정**할 수 있는 정형 검증 방법론
(고정 시나리오 · 지표 · 그라운드트루스 · 측정 하네스 · 현재 엔진 베이스라인 리포트) 설계·구현.
산출물: `src/scripts/verify_quality.py`(하네스), `data/ground_truth_labels.csv`(라벨), 본 문서.
근거: 현재 엔진(`src/backend/app/domain/selection.py`·`repo/song_repo.py`), 사용자 실패 피드백,
`docs/research/2026-07-11-playlist-sequencing-strategy.md`(§1.2 coherence, 부록 A 수식),
`docs/ref/user-opinion/2026-07-11-energy-sequencing-idea.md`.

---

## 0. 핵심 결론 (요약)

1. **검증이 이제 고정·재현 가능하다.** 대표 요청 **12개 시나리오**(params 고정 → LLM 없이 재현)를
   현재 엔진에 태워 **16개 지표**를 시드 20회 평균으로 산출하는 하네스를 구현했다. 앞으로의 모든
   엔진 변경은 `python src/scripts/verify_quality.py` 한 줄로 before/after 비교된다.
2. **무드 매칭은 이미 튼튼하다(그동안의 개선이 지표로 확인됨).** 조용/집중/발라드 요청에서
   그라운드트루스 '시끄러움' 곡 누출 **0건**, 최고강도 ≤ 0.28. 사용자가 지적한 무드 누출(処救生·
   灼熱·Steer to Utopia 유형)은 현재 엔진에서 재현되지 않는다 — 지표가 이를 정량 확인한다.
3. **가장 큰 잔여 약점은 "곡 경계 텐션 연속성"이다.** 12개 중 10개 시나리오에서
   `boundary_gap_mean` 게이트(≤0.30)를 미달(미달값 0.33~0.67). 어두움/클럽/상승 시나리오는 단일
   급전(`boundary_gap_max`) 최대 2.3(≈4σ)까지 튄다 — 사용자 케이스리포트의 "#1→#2 급락"이 지표로
   잡힌다. 엔진의 Stage B가 셔플 대비 개선은 하나(0.34 vs 셔플 0.52 vs 랜덤 0.70), 게이트엔 못 미친다.
4. **하모닉 전환율이 구조적으로 낮다(0.20~0.42).** Stage B가 하모닉을 경계 연속성에 종속시켜
   소프트 우선만 하므로, 재현실적 하한(0.35 = 랜덤 0.19의 약 2배)조차 9/12 미달. 연속성↔하모닉의
   설계상 상충 — 가중 재조정은 부장/사용자 결재 사항(§4.3).
5. **오프너 인트로 문제는 운동·상승 시나리오에서 재현된다.** `workout_burn` opener_intro −0.39,
   `rising_feelgood` −0.26(둘 다 게이트 미달) — 엔진이 첫 곡을 **인트로 텐션이 아니라 강도 근접**으로
   시드하기 때문(사용자 실패 #3).
6. **장르 미포착(클럽/파티)은 지표로 노출된다.** `gt_party_frac`가 파티/클럽 요청에서도 ≈0 —
   엔진에 "파티다움" 신호가 없고 강도로만 근사한다(사용자 실패 #6, 알려진 한계로 노출).

---

## 1. 방법론 개요 (왜 이 구성인가)

품질 검증은 네 조각으로 구성된다. 전부 **순수 함수 + CSV/엔진 출력**만 사용해 재현 가능하다.

```
고정 시나리오(12) ──params 고정──▶ build_setlist(seed 0..19) ──picks──▶ 지표(16) ──▶ 게이트(pass/fail)
        │                                                                    ▲
        └── 기대 속성(게이트 정의)                        그라운드트루스 라벨 ──┘
```

- **LLM을 제외한 이유**: LLM 해석은 비결정적이라 회귀 비교의 기준선이 흔들린다. 각 시나리오에
  `MoodParameters`를 **고정**해 선곡 엔진만을 결정적으로 측정한다(엔진이 품질의 원인이므로 옳은 경계).
  LLM 프롬프트 품질은 별도 티켓에서 측정.
- **시드 다중 평균**: 엔진은 Stage A 셔플·Stage B 랜덤창으로 매 요청 변주한다. 시드 0~19의 20회
  평균±표준편차로 **한 시나리오의 기대 품질**을 안정 추정한다(단발 실행의 우연 제거).

## 2. 고정 시나리오 셋 (Acceptance 1)

`src/scripts/verify_quality.py`의 `SCENARIOS`에 정의. 각 시나리오 = (a) 고정 params,
(b) profile(어떤 지표가 중요한지 결정), (c) 기대 속성(pass/fail 게이트, §4).

| id | 대표 요청 | profile | bright | E: start→end | N | 분 |
|---|---|---|---|---|---|---|
| quiet_calm | 조용하고 잔잔한 1시간 | quiet | +0.10 | 0.12→0.12 | 3 | 60 |
| focus_study | 차분하게 집중·공부 30분 | quiet | 0.00 | 0.15→0.15 | 2 | 30 |
| emotional_ballad | 감성적이고 애절한 발라드 40분 | quiet | −0.30 | 0.25→0.20 | 2 | 40 |
| rising_feelgood | 기분 좋아지는 점점 고조되는 1시간 | rising | +0.60 | 0.35→0.85 | 3 | 60 |
| gentle_morning | 잔잔히 시작해 서서히 깨어나는 아침 | rising | +0.40 | 0.20→0.55 | 3 | 45 |
| workout_burn | 운동·유산소로 불태울 45분 | rising | +0.30 | 0.65→0.90 | 3 | 45 |
| party_hype | 신나는 파티 45분 | party | +0.50 | 0.80→0.85 | 3 | 45 |
| club_music | 클럽 음악 45분 | party | +0.20 | 0.75→0.80 | 3 | 45 |
| dark_intense | 어둡고 강렬한 45분 | dark | −0.60 | 0.60→0.70 | 3 | 45 |
| bright_pop | 밝고 통통 튀는 팝 45분 | bright | +0.80 | 0.50→0.60 | 3 | 45 |
| wind_down | 하루 마무리, 점점 차분해지는 1시간 | descending | −0.10 | 0.60→0.20 | 3 | 60 |
| steady_drive | 드라이브용 적당히 신나는 일정한 1시간 | flat | +0.30 | 0.55→0.55 | 3 | 60 |

사용자가 예시한 요청 유형(조용/잔잔·신나는 파티·점점 고조·어둡고 강렬·집중/공부·운동·클럽)을 전부
포함하고, 아크 방향 4종(상승 rising·하강 descending·평탄 flat·근평탄 quiet/party)을 커버한다.

## 3. 그라운드트루스 라벨 (Acceptance 2)

`data/ground_truth_labels.csv` — idx 기준, 3개 dimension × 65개 라벨. 기존 `build_energy_full.py`의
36곡(조용/시끄러움/오판)을 **밝기·파티 dimension으로 확장**했다.

| dimension | label | 곡 수 | 근거 |
|---|---|---|---|
| intensity | quiet | 14 | 명백한 발라드/젠틀(栞·過惰幻·青い栞·鳥の詩 등). 데이터팀 GT_QUIET. |
| intensity | loud | 22 | 명백한 락/파티 앤섬 + 발췌오판(실제 시끄러움): FIRE BIRD·R・I・O・T·灼熱·はいよろこんで·黒 등. |
| brightness | bright | 8 | 밝은 장조 업텐포: hhw(やっほー·ハピネス·Happy!Happier!)·STAR BEAT·SAKURAスキップ. |
| brightness | dark | 8 | 어두운 고딕/단조: ave_mujica(Ave Mujica·神さま、バカ·Sophie)·roselia 다크·mygo(端程山). |
| party | party | 8 | 업비트 고에너지 댄서블: Time Lapse·Y.O.L.O·R・I・O・T·EXPOSE·灼熱·徒花ネクロマンシー. |
| party | calm | 5 | 잔잔한 비파티 발라드(栞·過惰幻·鳥の詩·ひまわりの約束·約束). |

**정직성 주의**: 라벨은 곡 정체성 기반의 **방향성 근거(소규모·수작업)** 이지 통계 유의성 주장이
아니다. 밝기 라벨은 밴드 정체성(hhw=해피, ave_mujica=고딕)에 근거하나 엔진 밝기(`mode_score` 파생)와
부분 상관이 있으므로 완전 독립 검증은 아니다 — 확장 시 사용자 청취 라벨링 권장. 파티 라벨은
**장르/댄서빌리티 피처 부재**로 강도에 근사한다(§0-6의 한계와 직결).

## 4. 지표 정의 (Acceptance 3) — 전부 순수 함수

`compute_metrics()`가 세트리스트 1건에 대해 계산. 피처는 엔진과 동일 근거:
`intensity`=`Song.energy`(다신호 soft-OR), `brightness`=`selection._brightness_scores`(−1~1),
`intro/outro`=`Song.intro_energy`/`outro_energy`(i_start/i_end, z-score 스케일 std≈0.6),
`camelot`→EPJ 3D 임베딩.

| 지표 | 정의 | 방향 | 대응 실패유형 |
|---|---|---|---|
| `mood_leak_rate` | 곡 강도가 소속 **단계 목표**에서 `LEAK_TOL=0.20` 초과 이탈한 곡 비율 | 낮을수록↑ | ①무드누출 |
| `gt_loud_in_setlist` | 그라운드트루스 '시끄러움' 곡 등장 수 | (조용 요청) 0이어야 | ①무드누출 |
| `max_intensity`·`mean_intensity` | 세트리스트 강도 최댓·평균 | 요청별 | ①무드누출 |
| `boundary_gap_mean`·`_max` | 인접쌍 `\|outro_i − intro_{i+1}\|`의 평균·최댓 | 낮을수록↑ | ②경계 텐션 |
| `bright_swing_mean`·`_max` | 인접쌍 `\|brightness_i − brightness_{i+1}\|` 평균·최댓 | 낮을수록↑ | ④밝기 급반전 |
| `opener_intro` | 첫 곡 인트로 텐션 | 파티/운동은 높게 | ③오프너 인트로 |
| `harmonic_rate` | 인접쌍 중 동일/인접 조성 비율 | 높을수록↑ | (하모닉 믹싱) |
| `arc_target_mae` | 단계별 실제 평균강도 vs 단계 목표의 평균 \|오차\| | 낮을수록↑ | ⑤아크 정합 |
| `arc_dir_consistency` | 단계 간 강도 변화가 요청 아크 방향과 일치하는 비율 | 높을수록↑ | ⑤아크 단조성 |
| `coh_energy`·`coh_brightness`·`coh_tonality` | EPJ 다양성정규화 응집성 `1 − (n/2)Σd(x_i,x_{i+1})²/Σ_{i<j}d²`, [−1,1] | 높을수록↑ | ②④ 전반 매끄러움 |
| `mean_brightness` | 세트리스트 평균 밝기 | 요청별(어두움↓밝음↑) | ④밝기 |
| `gt_party_frac` | 그라운드트루스 '파티' 앵커 비율 | (파티/클럽) 참고 | ⑥장르 미포착 |

**지표 타당성 검증**(하네스와 별도 확인): 랜덤 풀 경계갭 0.695 · 셔플(같은 곡 무작위순서) 0.522 ·
엔진 0.34 — 엔진이 실제로 경계를 좁힌다(지표가 순서 품질을 잡음). 랜덤 하모닉율 0.188 —
엔진 0.30 전후는 그 약 1.7배.

## 5. 측정 하네스 (Acceptance 4)

`src/scripts/verify_quality.py`. 엔진을 `sys.path` 삽입 후 `build_setlist`/`load_songs` import(수정
없음). 시드 고정(0..seeds−1) → 재현 가능. 주요 실행:

```
python src/scripts/verify_quality.py                    # 전 시나리오 스코어카드 + 게이트
python src/scripts/verify_quality.py --seeds 50         # 정밀(시드 50회 평균)
python src/scripts/verify_quality.py --scenario quiet_calm   # 단일 시나리오
python src/scripts/verify_quality.py --markdown --csv out.csv  # 보고표 + 원자료
```

---

## 6. 현재 엔진 베이스라인 스코어카드 (Acceptance 5)

**측정 대상 고정**: git HEAD `7b68366`("누락 밴드 포함 — various_artists·1곡 밴드 eligible 전환"),
`data/songs_master.csv` 660곡 **전곡 eligible**(직전 653 → 세션 중 부장 커밋으로 7곡 추가 편입).
시드 0~19 20회 평균. (전체 표준편차는 하네스 출력/`--csv` 참조.) 재실행: `python
src/scripts/verify_quality.py --seeds 20 --markdown`.

| scenario | profile | leak | gtLoud | maxI | meanI | bGapμ | bGapMax | bSwing | opnIntro | harm | arcMAE | arcDir | cohE | cohT | meanB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| quiet_calm | quiet | 0.00 | 0.00 | 0.20 | 0.14 | **0.34** | 1.29 | 0.13 | −1.02 | **0.34** | 0.02 | 1.00 | 0.03 | 0.13 | 0.16 |
| focus_study | quiet | 0.00 | 0.00 | 0.21 | 0.17 | **0.33** | 0.96 | 0.15 | −0.29 | **0.22** | 0.02 | 1.00 | 0.03 | 0.12 | 0.07 |
| emotional_ballad | quiet | 0.00 | 0.00 | 0.28 | 0.23 | 0.25 | 0.76 | 0.09 | 0.06 | **0.28** | 0.02 | 0.90 | 0.04 | −0.00 | −0.30 |
| rising_feelgood | rising | 0.00 | 0.00 | 0.92 | 0.59 | **0.39** | **1.74** | 0.08 | **−0.26** | 0.38 | 0.01 | 1.00 | 0.86 | 0.08 | 0.59 |
| gentle_morning | rising | 0.00 | 0.00 | 0.58 | 0.37 | **0.42** | 1.39 | 0.09 | −0.46 | **0.26** | 0.02 | 1.00 | 0.80 | 0.00 | 0.38 |
| workout_burn | rising | 0.00 | 0.00 | 0.90 | 0.75 | **0.38** | 1.30 | 0.09 | **−0.39** | **0.30** | 0.02 | 1.00 | 0.70 | 0.02 | 0.28 |
| party_hype | party | 0.00 | 0.55 | 0.93 | 0.85 | 0.26 | 0.68 | 0.08 | 0.38 | **0.26** | 0.03 | 1.00 | 0.29 | 0.01 | 0.47 |
| club_music | party | 0.00 | 0.00 | 0.85 | 0.77 | **0.42** | **1.76** | 0.08 | 0.65 | **0.32** | 0.02 | 0.68 | 0.12 | 0.12 | 0.19 |
| dark_intense | dark | 0.00 | 0.75 | 0.75 | 0.65 | **0.67** | **2.32** | 0.07 | 0.17 | 0.42 | 0.02 | 0.95 | 0.37 | 0.02 | −0.59 |
| bright_pop | bright | 0.00 | 0.00 | 0.65 | 0.55 | **0.40** | 1.26 | 0.08 | 0.03 | **0.29** | 0.02 | 0.98 | 0.39 | 0.05 | 0.77 |
| wind_down | descending | 0.00 | 0.30 | 0.65 | 0.42 | **0.34** | 1.08 | 0.08 | 0.03 | **0.25** | 0.02 | 1.00 | 0.87 | 0.14 | −0.11 |
| steady_drive | flat | 0.00 | 0.00 | 0.62 | 0.55 | **0.36** | 1.31 | 0.08 | 0.27 | 0.37 | 0.01 | 1.00 | −0.04 | 0.04 | 0.31 |

(**굵게** = 해당 시나리오의 게이트 위반 값. gtLoud는 파티/어두움/하강 요청에선 등장이 **정상**이라
비게이트 — 조용 요청에서만 0을 강제.)

## 7. 합격 임계값(게이트) 제안 (Acceptance 5)

임계값 근거: 스케일(intro/outro std≈0.6), 랜덤/셔플 베이스라인, 시퀀싱 보고서 §3.

**공통 게이트(전 시나리오):**
| 게이트 | 임계 | 근거 |
|---|---|---|
| `boundary_gap_mean` | ≤ 0.30 | ≈0.5σ. 셔플 0.52·랜덤 0.70 대비 유의미 개선선. |
| `boundary_gap_max` | ≤ 1.50 | ≈2.5σ. 사용자가 체감하는 "튀는 단일 전환" 상한. |
| `harmonic_rate` | ≥ 0.35 | 랜덤 0.19의 약 2배(현실적 하한; 0.50은 연속성과 상충 — §4.3). |
| `bright_swing_mean` | ≤ 0.60 | 인접 밝기 평균 급변 상한. |

**profile별 게이트:**
| profile | 추가 게이트 |
|---|---|
| quiet | `max_intensity ≤ 0.30~0.45`, `gt_loud_in_setlist == 0`, `mean_intensity ≤ target+0.10` |
| rising/descending | `arc_dir_consistency ≥ 0.99`, `arc_target_mae ≤ 0.15` |
| party/workout | `opener_intro ≥ 0.20~0.30`, `mean_intensity ≥ 0.60~0.65` |
| dark | `mean_brightness ≤ −0.20`, `mean_intensity ≥ 0.50` |
| bright | `mean_brightness ≥ 0.30` |
| flat | `arc_target_mae ≤ 0.12` |

**게이트 통과 요약(현재 엔진, HEAD 7b68366): 전체 51/75.**

| scenario | 통과 | 취약 지표 |
|---|---|---|
| quiet_calm | 6/8 | boundary_gap_mean, harmonic_rate |
| focus_study | 5/7 | boundary_gap_mean, harmonic_rate |
| emotional_ballad | 5/6 | harmonic_rate |
| rising_feelgood | 4/7 | boundary_gap_mean/max, **opener_intro** |
| gentle_morning | 4/6 | boundary_gap_mean, harmonic_rate |
| workout_burn | 4/7 | boundary_gap_mean, harmonic_rate, **opener_intro** |
| party_hype | 5/6 | harmonic_rate |
| club_music | 3/6 | boundary_gap_mean/max, harmonic_rate |
| dark_intense | 4/6 | boundary_gap_mean/max |
| bright_pop | 3/5 | boundary_gap_mean, harmonic_rate |
| wind_down | 4/6 | boundary_gap_mean, harmonic_rate |
| steady_drive | 4/5 | boundary_gap_mean |

## 8. 약점 진단 (어느 시나리오/지표가 취약한가)

1. **경계 텐션 연속성 — 최대 약점(10/12 미달).** `boundary_gap_mean` 0.25~0.67(미달값 0.33~0.67).
   특히 후보가 넓게 퍼지는 **어두움·클럽·상승** 시나리오에서 `boundary_gap_max`가 1.7~2.3(≈3~4σ)로
   튄다. 원인:
   Stage B가 (a) 단계 *내부*만 연속 체인을 걸고 (b) `_CONT_WINDOW=0.15` 슬랙 + 랜덤 선택으로
   최소화를 느슨하게 하며 (c) 단계 경계 접합이 seed 1곡만 맞춘다. → 사용자 케이스리포트의
   "#1(하이텐션)→#2(조용한 인트로) 급락"이 그대로 재현·계량된다. **개선 여지 최상.**
2. **하모닉 전환율 — 구조적 저하(9/12 미달, 0.35 기준).** Stage B가 하모닉을 경계 연속성에
   종속시켜(호환 후보가 창 안에 있을 때만 우선) 0.20~0.42. `coh_tonality`도 0.03~0.13으로 낮아
   조성 배열이 거의 무작위 수준임을 재확인. **연속성↔하모닉 상충** — 둘 다 올리려면 Stage B를
   다목적(경계갭 + 조성거리) 정렬로 바꿔야 하며, 가중은 결재 사항.
3. **오프너 인트로 — 운동/상승에서 취약.** `workout_burn` opener_intro −0.39, `gentle_morning`
   −0.46, `rising_feelgood` −0.26(게이트 미달). 엔진이 첫 곡을 **강도 근접**으로 시드
   (`min|energy−target|`)해 인트로 텐션을 보지 않는다. 파티(0.38)·클럽(0.65)은 통과하나 편차가
   크다(±0.6~0.8). → 사용자 실패 #3 재현. 첫 스테이지 seed를 "강도 부합 ∧ 인트로 텐션 높음"으로
   바꾸면 해소.
4. **장르 미포착 — 지표로 노출된 한계.** `gt_party_frac`가 party_hype/club_music에서도 ≈0.
   엔진에 "파티/클럽다움" 신호가 없어 강도로만 근사 → 파티 앵커를 특별히 끌어오지 못한다(장르/
   댄서빌리티 피처 부재, 사용자 실패 #6). 재추출(장르 태그/댄서빌리티) 전까지 알려진 한계.
5. **무드 누출 — 현재 강점(취약 아님).** 조용/집중/발라드에서 gt_loud 누출 0, max_intensity ≤0.28.
   그동안의 강도 재추출(energy_full·i_min·i_end soft-OR)이 지표로 검증됐다. `mood_leak_rate`가
   전 시나리오 0인 것은 Stage A가 tol=0.08로 하드 선택하기 때문(단계 목표 대비 누출 구조적 차단).
   → 이 지표는 **밴드 필터로 풀이 희박해지거나 미래 엔진이 선택을 느슨히 할 때의 회귀 가드**로 유효.
6. **coherence의 착시 유의.** `coh_energy`가 평탄/조용 시나리오에서 ≈0(quiet_calm −0.04, steady 0.06)
   인 것은 "덜 매끄럽다"가 아니라 **강도 다양성이 작아 정규화 분모가 작기 때문**(시퀀싱 보고서 §3.3).
   상승/하강에선 0.70~0.88로 정상적으로 높다. coh_energy는 **아크 시나리오에서만** 배열 품질 신호로
   해석하고, 평탄/조용에선 `boundary_gap`을 주지표로 볼 것.

## 9. 회귀 테스트 고정 권고 (Acceptance 6, 선택)

향후 엔진 변경 시 **반드시 통과**해야 할 핵심 게이트(회귀 스냅샷 후보):

| 우선 | 게이트 | 이유 |
|---|---|---|
| 필수 | `quiet_calm/focus_study: gt_loud_in_setlist == 0`, `max_intensity ≤ 0.30` | 무드 누출 회귀 방지(현재 강점 사수). |
| 필수 | 전 시나리오 `arc_target_mae ≤ 0.15`, 상승/하강 `arc_dir_consistency ≥ 0.99` | 아크 정합 회귀 방지(현재 통과). |
| 개선추적 | `boundary_gap_mean ≤ 0.30`, `boundary_gap_max ≤ 1.5` | 현재 미달 — 개선 목표선. 값이 낮아지면 승격. |
| 개선추적 | `harmonic_rate ≥ 0.35` | 현재 미달 — 연속성 절충 결정 후 확정. |
| 개선추적 | `workout_burn: opener_intro ≥ 0.20` | 현재 미달 — 오프너 시드 규칙 개선 목표. |

권고: **필수 게이트만 `src/tests/`에 시드 고정 pytest로 고정**하고(회귀 방지), **개선추적 게이트는
본 하네스로 수치 추적**(before/after)한다. 하네스는 코드팀 티켓에서 pytest로 이관 가능.

---

## 10. 보고 (R4 형식)

**목표.** 플레이리스트 품질을 객관적·반복 측정하는 정형 검증 방법론(고정 시나리오 + 지표 +
그라운드트루스 + 측정 하네스 + 현재 엔진 베이스라인)을 설계·구현.

**수행 내용.**
- 현재 엔진(selection.py 2단계 SELECT→SEQUENCE, song_repo 다신호 강도) 정독 → 측정 지점 도출.
- 고정 시나리오 12개(params 고정, profile·게이트 포함) 정의: `verify_quality.py::SCENARIOS`.
- 그라운드트루스 3 dimension 65 라벨 생성(기존 36곡 → 밝기·파티 확장): `data/ground_truth_labels.csv`.
- 지표 16종 구현(무드누출·경계연속성·밝기급변·오프너·하모닉·아크정합/단조·EPJ coherence 3종 등),
  전부 순수 함수. EPJ coherence·조성 3D 임베딩은 시퀀싱 보고서 §1.2/부록 A 수식 그대로.
- 측정 하네스 구현(시드 20회 평균, 스코어카드·게이트·마크다운·CSV 출력): `src/scripts/verify_quality.py`.
- 지표 타당성 별도 검증(랜덤/셔플 베이스라인 대비 엔진의 경계갭·하모닉 개선 확인).
- 현재 엔진 전 시나리오×지표 베이스라인 스코어카드 + 게이트 임계값 제안 + 약점 진단 작성(본 문서).

**완료 목록.**
- [x] 고정 시나리오 셋 12개 (Acceptance 1)
- [x] 그라운드트루스 라벨 65개 CSV (Acceptance 2)
- [x] 지표 16종 정의·구현(순수 함수) (Acceptance 3)
- [x] 측정 하네스 `verify_quality.py`(시드 고정 다중평균·재현) (Acceptance 4)
- [x] 현재 엔진 베이스라인 리포트 + 게이트 임계값 + 약점 진단 (Acceptance 5)
- [x] 회귀 테스트 핵심 게이트·임계값 권고 (Acceptance 6)
- [x] R6/R11 준수: 쓰기는 `src/scripts/`·`docs/research/`·`data/`만, `src/backend/` 무수정(import 호출만),
  git 미실행, 서브에이전트 미스폰.

**미완료 / 한계 (정직 보고).**
- [ ] **그라운드트루스 소규모·수작업(65)** — 방향성 근거이지 통계 유의성 아님. 밝기 라벨은 엔진
  밝기(mode_score 파생)와 부분 상관 → 완전 독립 아님. 확장하려면 사용자 청취 라벨링 필요.
- [ ] **파티/장르 지표는 강도 근사** — 장르/댄서빌리티 피처가 없어 `gt_party_frac`가 base-rate에
  묶여 ≈0. 클럽/파티 "장르 적합성"의 진짜 측정은 재추출(장르 태그) 후에나 가능.
- [ ] **밝기 아크(시간축 밝기 변화) 시나리오 미포함** — 현재 아크는 강도축만. 대칭 확장 가능하나
  본 티켓 범위 밖.
- [ ] **하네스→pytest 회귀 고정은 미실행** — R&D는 방법론·베이스라인까지. 실제 `src/tests/` 픽스처
  고정은 코드팀 쓰기 권한. §9에 필수 게이트를 이관 명세로 남김.
- [ ] **엔진 개선 자체는 미수행** — 본 티켓은 "측정 방법론". 진단된 약점(경계연속성·하모닉·오프너
  시드)의 실제 수정은 후속 엔진 티켓.

**미완료 사유.** (a) 코드팀 영역(`src/backend/`·`src/tests/`) 쓰기 권한 밖 → 개선·pytest 고정은
이관. (b) 장르/청취 라벨은 재추출·사용자 자원 필요 → 파일럿 실사용 데이터로 후속.

**다음 단계 제안.**
1. **부장/사용자 결재**: (i) 게이트 임계값 확정(특히 boundary_gap·harmonic_rate 목표선),
   (ii) 연속성↔하모닉 상충에서 어느 쪽 가중을 올릴지.
2. **코드팀(엔진 티켓)**: §8 약점 순 개선 — ① Stage B 경계 최소화 강화(랜덤창 축소 + 단계 경계
   접합 개선), ② 오프너 seed를 "강도 부합 ∧ 인트로 텐션 높음"으로, ③ 하모닉을 경계갭과 함께
   다목적 정렬. **각 변경마다 `verify_quality.py`로 before/after 비교.**
3. **코드팀**: §9 필수 게이트를 `src/tests/`에 시드 고정 pytest로 고정(무드누출·아크 회귀 방지).
4. **데이터팀(재추출 시)**: 장르 태그/댄서빌리티 → `gt_party_frac`를 진짜 장르 지표로 승격.
5. **파일럿 후**: 실사용 청취 로그로 그라운드트루스 확장 → 밝기·파티 라벨 독립성 확보.
