# method-13 — 사용가능 지표 간 다중공선성 확인

## 대상
`report_feats.md`(2026-08-02) "사용가능" 분류 8개 지표, 736곡 전수(결측 없음):
`m4-lufs_integrated`, `m4-lra`, `m5-arousal_median`, `m6-valence_median`,
`m7-danceability_norm`, `m9-instr_stem_ratio`, `m8-acoustic_median`, `m11-speech_median`
(+ 참고용으로 `m3-mode`를 major=1/minor=0 이진 인코딩해 상관행렬에만 포함, VIF 계산에서는 제외)

## 결론 먼저 — 다중공선성 문제 없음

VIF(분산팽창지수) 전부 **5 미만**(통상 주의 기준). 최댓값도 3.32로 "약한 상관은
있지만 심각한 중복은 아님" 수준. 범주형 `m3-mode`(major=1/minor=0 이진 인코딩)를
포함한 9개 지표 전부 leave-one-out 방식(나머지 8개로 선형회귀)으로 동일하게 계산.

| 지표 | R²(나머지로 예측) | VIF |
|---|---|---|
| `m5-arousal_median` | 0.699 | **3.32** |
| `m4-lufs_integrated` | 0.494 | 1.98 |
| `m6-valence_median` | 0.447 | 1.81 |
| `m7-danceability_norm` | 0.410 | 1.70 |
| `m8-acoustic_median` | 0.372 | 1.59 |
| `m4-lra` | 0.359 | 1.56 |
| `m11-speech_median` | 0.288 | 1.40 |
| `m3-mode`(binary) | 0.106 | **1.12** |
| `m9-instr_stem_ratio` | 0.097 | 1.11 |

- `m9-instr_stem_ratio`와 `m3-mode`가 가장 독립적(VIF 1.10~1.12) — 다른 지표들로는
  거의 설명 안 됨, 선곡 가중치에서 고유한 정보량을 갖는다고 볼 수 있음.
- `m5-arousal_median`이 가장 다른 지표들과 얽혀 있음(VIF 3.32) — 그래도 5 미만이라
  "제거해야 할 수준"은 아니고, 여러 지표의 공통 성분(에너지감)을 부분적으로 대표하는
  것으로 해석 가능.
- **`m3-mode`(범주형)**: 이진 인코딩 특성상 선형 VIF가 이론적으로 완벽히 들어맞는
  지표는 아니지만(로지스틱 방식이 더 정확), 개별 상관계수 자체가 전부 |r|<0.21로
  작아 결론이 달라질 가능성은 낮음. 나머지 8개 지표와 가장 강한 상관은
  `m6-valence_median`(r=+0.204, major일수록 밝은 정서 쪽) — REPORT.md에서 확인된
  "major 밴드=밝은 컨셉" 패턴과 정합적이나 크기 자체는 약함.

## Pearson 상관행렬에서 눈에 띄는 쌍 (|r| > 0.4)

| 지표 A | 지표 B | r | 해석 |
|---|---|---|---|
| `m5-arousal_median` | `m8-acoustic_median` | **-0.596** | 각성도 높을수록 어쿠스틱 확률 낮음(당연: 전자음/밴드사운드=고에너지) |
| `m5-arousal_median` | `m4-lufs_integrated` | **+0.580** | 각성도 높을수록 더 크게 마스터링(에너지-라우드니스 결합, 예상된 관계) |
| `m6-valence_median` | `m7-danceability_norm` | +0.449 | 밝은 곡일수록 리듬감 있게 판정 |
| `m4-lra` | `m7-danceability_norm` | -0.440 | 다이내믹 범위 좁을수록(다이내믹스 압축) 댄서블 판정 높음 |
| `m11-speech_median` | `m7-danceability_norm` | +0.416 | 음절밀도 높은(속사포) 곡이 댄서블로도 판정되는 경향 |
| `m5-arousal_median` | `m4-lra` | -0.467 | 각성도 높을수록 다이내믹 범위 좁음(압축된 고에너지 믹스) |
| `m5-arousal_median` | `m6-valence_median` | +0.417 | 각성도-정서밝기 약한 동행(661/736곡 특성상 "밝고 격한" 곡이 많음을 시사) |

- 전부 |r|<0.6으로, 흔히 쓰는 "문제 있는 상관" 기준(|r|>0.8~0.9)에는 크게 못 미친다.
- 다만 `arousal`-`acoustic`, `arousal`-`lufs`, `arousal`-`lra` 세 쌍은 **arousal이
  이 세 지표의 공통 축(에너지/라우드니스/압축도)을 상당 부분 흡수**하고 있다는 뜻이라,
  VIF가 arousal에서 가장 높게 나온 것과 정합적이다.

## 실무 시사점

- **9개 지표(연속 8개 + 범주형 mode)를 그대로 다 선곡 가중치에 넣어도 통계적으로
  심각한 중복(다중공선성)은 없다** — 회귀/가중합 모델에 넣을 때 계수가 불안정해질
  위험은 낮음.
- 다만 `m5-arousal_median`을 다른 에너지 계열 지표(`m4-lufs_integrated`, `m4-lra`,
  `m8-acoustic_median`)와 **동시에 강한 가중치**로 쓰면 사실상 "에너지"라는 하나의
  개념을 4번 겹쳐 세는 셈이 될 수 있어 튜닝 시 주의가 필요하다(통계적 문제라기보다
  개념적 중복 위험).
- `m9-instr_stem_ratio`는 다른 어떤 지표와도 잘 안 겹치므로(VIF 1.10, 최대 |r|=0.17)
  독립적인 축으로 안심하고 추가 가중치를 줄 수 있다.

## `m3-mode`는 다중공선성과 별개로 선곡 파라미터에서 제외 권고 (2026-08-02)

VIF·상관관계상으로는 `m3-mode`가 문제없지만(오히려 가장 독립적인 축 중 하나),
**앱의 연속형 선곡 가중치 파라미터로 쓰기엔 부적합**하다고 판단한다 — 통계적
다중공선성과는 별개의, 파라미터 설계 관점의 문제다.

- `m3-mode`는 major/minor 이진값이라, 슬라이더처럼 연속적으로 조절되는 다른 8개
  지표와 함께 가중합에 넣으면 "약간 더 밝은 느낌" 같은 중간 정도의 선호를 표현할
  수 없다 — 항상 한쪽으로 완전히 쏠린 곡만 골리는 전부-아니면-전무(all-or-nothing)
  방식이 되어 다른 연속 지표들과 결이 다르다.
- 대안으로 "major 상관 − minor 상관" 마진 같은 연속 점수를 만들 수도 있지만,
  현재 `data/all_features.csv`에는 최고 상관 템플릿만 이산화되어 저장돼 있고
  (`m2-key_ks`/`m2-mode_ks`), 원본 상관계수 자체는 저장돼 있지 않아 재추출이
  필요하다 — 이번 라운드에서는 착수하지 않는다.
- **권고**: `m3-mode`는 9개 지표 가중합 파라미터에서 제외하고, 연속 8개
  (`m4-lufs_integrated`, `m4-lra`, `m5-arousal_median`, `m6-valence_median`,
  `m7-danceability_norm`, `m8-acoustic_median`, `m9-instr_stem_ratio`,
  `m11-speech_median`)만 파라미터로 사용한다. `m3-mode`는 필요하다면 `m8-acoustic_median`과
  같은 급의 **필터/태그 전용**(예: "단조 곡만 보기" 옵션)으로 남겨두는 정도로 제한한다.

## `m8-acoustic_median` UI 설계 — ON/OFF 토글 권고, 3분류는 비권장 (2026-08-02)

`out/fig/feature_distributions.png`에서 확인했듯 `m8-acoustic_median`은 8개 연속
지표 중 유일하게 극단적으로 첨도(kurtosis)가 높은 분포다 — 690/736곡(94%)이 거의 0에
몰려있고 나머지가 0.4~1.0에 소수 이상치로 존재. 나머지 7개 지표(`m4-lufs_integrated`,
`m4-lra`, `m5-arousal_median`, `m6-valence_median`, `m7-danceability_norm`,
`m9-instr_stem_ratio`, `m11-speech_median`)는 대체로 종형 또는 균등분포라 슬라이더형
UI로 사용자가 값을 점진적으로 조절하도록 유도하기 적합하지만, `acoustic_median`은
분포 특성상 "조절"이 체감되지 않는다(대부분의 슬라이더 구간이 사실상 같은 결과를 냄).

- **3분류(ALL/NON-ACOUSTIC/ACOUSTIC)는 비권장**: 카탈로그의 94%가 이미 NON-ACOUSTIC
  이므로 ALL과 NON-ACOUSTIC 두 옵션이 결과상 거의 동일해져 사용자에게 중복 선택지로
  느껴질 위험이 크다.
- **권고안**: 슬라이더가 아닌 **이진 토글**("어쿠스틱 버전만 찾기" ON/OFF) 하나로
  단순화한다. OFF = 전체 카탈로그(필터 없음), ON = `acoustic_median > 0.10` 임계값
  이상인 이상치 곡만(커버/"Acoustic Ver." 태그 곡 중심)으로 좁힌다. 이는 연속 가중치
  파라미터 목록에서 빼고 별도의 필터 옵션으로 다루는 기존 방침(`report_feats.md`의
  "필터 전용" 분류)과도 일관된다.

## 나머지 7개 연속 지표의 UI 설계 — 전부 백분위 순위(percentile rank)로 통일 권고 (2026-08-02)

`acoustic_median`을 제외한 7개 연속 지표의 왜도(skewness)·초과첨도(excess kurtosis)를
확인했다(736곡, `scipy.stats.skew`/`kurtosis`).

| 지표 | skewness | excess kurtosis | 형태 |
|---|---|---|---|
| `m7-danceability_norm` | -0.02 | -1.20 | 완전 uniform |
| `m6-valence_median` | -0.32 | -0.39 | 거의 정규분포 |
| `m11-speech_median` | +0.69 | 1.04 | 약한 오른쪽 skew, 종형 |
| `m9-instr_stem_ratio` | -0.56 | 1.95 | 약한 왼쪽 skew, 종형 |
| `m5-arousal_median` | -1.76 | 5.78 | 중간 skew(왼쪽 꼬리) |
| `m4-lra` | +2.36 | 7.92 | 뚜렷한 오른쪽 긴 꼬리(chi-square형) |
| `m4-lufs_integrated` | -3.21 | 18.83 | 뾰족한 봉우리+왼쪽 극단 이상치(스파이크형) |

- `m7-danceability_norm`이 유일하게 완전한 uniform인 이유는 이 컬럼 자체가 이미
  "카탈로그 내 백분위 순위"로 정규화되어 산출된 지표이기 때문이다(method-7
  findings: "표본 내 상대순위가 절대값보다 유용, 카탈로그 확장에도 안정적").
- `m4-lra`·`m5-arousal_median`·`m4-lufs_integrated`처럼 skew·kurtosis가 뚜렷한
  지표를 원값 그대로 0~100 슬라이더에 매핑하면, 사용자가 특정 구간(예: 상위 20)을
  선택했을 때 실제 후보곡 수(n)가 지나치게 적어지는 문제가 생길 수 있다.
- `m6-valence_median`·`m11-speech_median`·`m9-instr_stem_ratio`는 이미 종형에
  가까워 원값을 그대로 써도 큰 문제는 없지만, 백분위 변환을 적용해도 원값과 거의
  선형에 가깝게 매핑되므로(왜곡이 작음) **손해가 없다**.

**권고**: UI 일관성을 위해 **7개 연속 지표 전부를 백분위 순위(0~100%) 기준으로
통일**한다. `m7-danceability_norm`은 이미 이 방식으로 만들어져 있으니 그대로 두고,
나머지 6개(`m4-lufs_integrated`, `m4-lra`, `m5-arousal_median`, `m6-valence_median`,
`m9-instr_stem_ratio`, `m11-speech_median`)도 동일한 변환(예: `rank(pct=True)` 또는
`scipy.stats.percentileofscore`)을 적용해 슬라이더에 노출한다. 이렇게 하면:
- 슬라이더 어느 구간을 선택해도 항상 비슷한 밀도의 후보곡이 걸림(왜곡된 분포 때문에
  특정 구간에서 후보가 텅 비는 문제 방지).
- 서로 다른 단위(LUFS dB, 0~9 스케일, 0~1 비율 등)를 가진 지표들이 전부 동일한
  0~100 UI 규칙을 따르게 되어 사용자·개발자 모두 예외를 기억할 필요가 없음.

**트레이드오프**: 백분위 변환은 절대적 단위 의미(예: 실제 LUFS 값)를 잃고, 카탈로그에
곡이 추가될 때마다 순위가 재계산돼야 한다(`danceability_norm`이 이미 이 방식으로
운영 중이므로 선례는 있음).

## 산출물
- `out/csv/correlation_pearson.csv`, `out/csv/correlation_spearman.csv`
- `out/csv/vif.csv`
- `out/fig/correlation_heatmap.png`
- `out/fig/feature_distributions.png`, `out/fig/feature_distributions_by_band.png`
