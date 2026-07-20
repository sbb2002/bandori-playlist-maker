# 전체 피쳐 분포 스캔 + 밴드별 특징 신호

`report/02`(method-2 BPM 확정) 이후, `audio_feats.csv`의 전체 수치형 피쳐를 훑어보고
밴드(장르 정체성)와의 관계를 확인한 결과다. 오디오 재처리 없음 — 기존 CSV(`out/audio_feats.csv`,
`out/bpm_final.csv`)만 사용.

## 1. 방법

### 1.1 대상 컬럼
`audio_feats.csv`(661곡, 103컬럼) 중 식별자·상수·불리언 컬럼을 제외한 **89개 수치형 컬럼**
(`final_bpm`은 `bpm_final.csv`에서 병합해 대표 템포로 포함). 음향 지표 감사에서 신뢰 불가로
확인된 8개 컬럼(`energy`,`energy_proxy`,`energy_proxy_proxies`,`mode_score`,`mode_score_proxies`,
`pct_major`,`chord_change_rate`,`borrowed_chord_rate`)은 그래프에서 빨간 테두리로 별도 표시.

### 1.2 시각화 — small multiples
컬럼당 미니 히스토그램(16-bin) + mean/median/skew를 6열 그리드로 배열. 1차로 밴드 구분 없는
버전, 2차로 밴드별 stacked-bar 색칠 버전을 만들었다. 밴드는 13개(9개 게임 수록 밴드 +
`various_artists`/`ikka_dumb_rock`/`millsage`/`mugendai_mutype`)인데, 카테고리 팔레트 안전
한도(스택형 인접비교 기준 8색)를 넘어서 **곡 수 상위 8개 밴드만 개별 색상, 나머지 5개는
"Other"로 통합**했다.

- Fig 1(밴드 구분 없음): `fig/feature_distributions_grid.png`
- Fig 2(밴드별 색칠): `fig/feature_distributions_by_band.png`

육안 스캔만으로는 89개가 한 화면에 몰려 있어 밴드 간 차이가 두드러지지 않았다 — 정보 과다로
희석된 것이지 실제로 차이가 없는 건 아니었다(§2 참조).

### 1.3 정량 검증 — 밴드 간 분산 비율(ANOVA eta²)
육안으로 안 보이는 신호를 잡기 위해, 상위 8개 밴드 + Other 그룹 기준으로 `scipy.stats.f_oneway`와
eta²(밴드가 설명하는 분산 비율)를 89개 컬럼 전체에 대해 계산했다.

## 2. 결과

### 2.1 밴드가 가장 크게 갈리는 피쳐 (eta² 상위, 신뢰 가능 컬럼만)

| 컬럼 | eta² | 의미 |
|---|---|---|
| `mfcc_4_mean` | **0.456** | 밴드가 분산의 45.6% 설명 — 음색 차이가 밴드별로 가장 뚜렷 |
| `perc_p90` | 0.365 | 타악기 강도 90백분위 |
| `perc_p95` | 0.344 | 타악기 강도 95백분위 |
| `mfcc_7_mean` | 0.332 | 음색 |
| `mfcc_10_mean` | 0.323 | 음색 |
| `energy_full` | 0.305 | 유일하게 신뢰 가능한 에너지 지표 |
| `mfcc_13_mean` | 0.291 | 음색 |
| `harmonic_ratio` | 0.281 | 하모닉 비율 |
| `rms`/`rms_mean` | 0.278/0.269 | 음량(RMS) |

### 2.2 밴드별 특징 요약 (z-score 기준, |z|>0.8을 유의미로 판단)

| 밴드 (n) | 눈에 띄는 특징 | 해석 |
|---|---|---|
| morfonica (57) | 타악기 최저(z=−2.2), 하모닉비율 최고(+2.1), mfcc_4 최고(+1.9) | 오케스트라·선율 중심, 타악기 비중 낮음 |
| mygo (44) | RMS 최고(+2.5), energy_full 최저(−2.0), lufs 최고(+2.3) | RMS·라우드니스는 최고인데 energy_full은 최저 — 조용~폭발 다이나믹 대비가 큰 편곡 특성으로 추정 |
| hello_happy_world (72) | onset_p90 최고(+2.0), mfcc_9_std 최고(+2.2), final_bpm 최저(−1.7) | 리듬·음색 변화는 최대인데 평균 템포는 최저 — 싱커페이션 중심 편곡 |
| pastel_palettes (74) | zcr_p90 최고(+1.5), energy_full 상위(+1.1) | 밝고 노이즈성 있는 고음역(신스팝) 비중 높음 |
| afterglow (72) | final_bpm 최고(+1.3) | 9개 밴드 중 평균 템포 최고 |
| raise_a_suilen (79) | mfcc_4 최저(−1.8), contrast 최저(−1.4) | 두꺼운 음색·낮은 대비 — 록/메탈 계열 밀도 높은 사운드 |
| roselia (89) | i_max 낮음(−1.1) | 뚜렷한 극단값 없음, 다이나믹 피크가 낮은 편 |
| poppin_party (115) | 전 지표 \|z\|<0.6 | 이 카탈로그의 "기준점" — 어떤 지표로도 튀지 않는 장르 중립 팝 |
| **ave_mujica (29)** | energy_full 최저권(−1.28), perc_p90/95 낮음(≈−1.0) | Other에 묻혀 Fig 2엔 안 보이지만 조용하고 덜 타격적인 편곡 신호 뚜렷 |
| **mugendai_mutype (23)** | mfcc_4 최저(−1.27), 타악기 상위(≈+1.0) | raise_a_suilen과 유사한 "두꺼운 음색+타격감" 계열 |
| various_artists (5) | — | 표본 부족(5곡), 밴드 정체성 자체가 성립 안 함(여러 아티스트 혼합) |
| ikka_dumb_rock (1) | — | 곡 1개, 통계적 의미 없음 |
| millsage (1) | — | 곡 1개, 통계적 의미 없음 |

**주의**: ave_mujica/mugendai_mutype은 Fig 2의 "Other" 범례 뒤에 숨어 있지만 실제로는
표본이 충분하고(각 29곡/23곡) 신호도 뚜렷하다 — 그래프에 안 보인 건 팔레트 8색 한도 때문이지
실제로 특징이 없어서가 아니다. 반면 various_artists 이하 3개 밴드는 표본 자체가 통계적으로
무의미한 수준(1~5곡)이라 "Other" 통합이 정보 손실 없이 타당하다.

## 3. 결론

1. **89개 피쳐를 한 화면에서 육안으로 스캔하는 것만으론 밴드 신호가 안 보인다** — ANOVA로
   정량화해야 잡히는 수준의 신호였다.
2. **밴드(장르 정체성)가 음색(MFCC)·타악기·에너지 지표에 뚜렷이 새겨져 있다.** 특히
   `mfcc_4_mean`은 밴드 하나로 분산의 45.6%가 설명될 만큼 강한 신호.
3. **mygo의 RMS-energy_full 괴리**(§2.2)는 별도로 파볼 가치가 있다 — 두 에너지 계열
   지표가 밴드 하나에서 정반대로 갈리는 건 계산 방식 차이인지 실제 다이나믹 편곡 특성인지
   아직 미확인.
4. **"Other" 통합은 팔레트 제약에 따른 시각화 설계 산물**이지 데이터 부족의 결과가 아니다 —
   ave_mujica·mugendai_mutype은 개별 분석 시 뚜렷한 신호가 있었다. 반면 곡 1~5개짜리 소수
   밴드는 진짜 표본 부족.

## 4. 산출물
- Fig 1: `fig/feature_distributions_grid.png` (밴드 구분 없음, 89개 컬럼)
- Fig 2: `fig/feature_distributions_by_band.png` (밴드별 stacked, 상위 8밴드 + Other)
- 이 리포트의 수치는 `out/audio_feats.csv` + `out/bpm_final.csv` 기준 즉석 계산(별도 out/ 파일
  미생성) — 재현 시 §1의 pandas/scipy 스니펫 참조.
