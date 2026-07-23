# n≥20 라운드 분석 스펙 사전등록

> GEMS-9 채점 데이터를 보기 전에 동결한다(통계 자문 report/04 §3의 "절차적 위생" 반영).
> 여기 적힌 값을 데이터를 본 뒤에 바꾸면 안 된다 — 바꿀 필요가 생기면 그 사실과 이유를
> 이 문서에 추가하고(덮어쓰지 않고) 최종 보고서에 명시한다.

## 1. 표집 (이미 실행·동결됨)

- 시드: `20260723` (`build_gems9_n20_candidates.py` 내 `SEED` 상수).
- 모집단: `eligible_band==True` 중 15곡 미만 밴드·`various_artists` 제외 → 10개 밴드 654곡.
- 균형표집 기준축: 19개 후보 피쳐(MFCC 13종 + contrast_mean + energy_full + rms_mean +
  bpm + mode_score + tempo_bpm) 표준화 후 PCA의 **PC1 1개만** 사용.
- 삼분위 경계: 밴드마다 그 밴드 소속곡의 PC1 값으로 `pandas.qcut(..., 3)` — **밴드별로
  독립적으로** 계산(카탈로그 전체 경계 아님).
- 밴드별 목표곡수: 비례배분 + floor=4, largest remainder로 정수화, 총 70곡.
- 홀드아웃: 본표본 추출 직후 같은 RNG 인스턴스를 이어서 사용, 목표 25곡(floor=2), 본표본과
  disjoint 구조적 보장.
- 산출물(이미 고정): `out/gems9_n20_candidates.csv`, `out/gems9_n20_holdout_sealed.csv`,
  `out/gems9_n20_representative_features.csv`(17개 대표 피쳐).

## 2. 대표 피쳐 목록 (동결)

`out/gems9_n20_representative_features.csv`의 `is_representative==True` 17개 피쳐를
그대로 쓴다. 클러스터링 임계값(거리=1-|Spearman rho|, cutoff=0.3)도 고정.

## 3. 불완전블록 (이미 실행·동결됨)

- 블록 크기 30, 원형 슬라이딩 윈도로 자동 생성된 블록 수(현재 5개).
- 응답자 수 목표 `N_RATERS=22`(`assign_rater_blocks.py`), 곡당 최소 응답자 수 기준 5명.
- 재시드 허용 사유는 **연결성 미충족 또는 곡당 최소응답자수 미달** 둘뿐 — 그 외 사유로
  재실행하지 않는다.

## 4. 평정자 효과 제거 모형 (분석 전 동결)

- 명세: `{gems_item} ~ C(rater_id)`, `groups = song_idx`(랜덤절편만, `re_formula` 기본값),
  REML 추정(`statsmodels.formula.api.mixedlm`).
- rater는 고정효과, song은 랜덤효과 — crossed random effects의 간소화판이며, 목적은
  "이 22명의 평정자 개인차(nuisance)를 곡 점수에서 제거"이지 평정자 모집단에 대한 일반화가
  아니므로 이 간소화를 채택한다(report/04 §2 라운드3 참고).
- 곡별 조정점수 = 고정효과 절편(`Intercept`) + 그 곡의 랜덤절편(BLUP).

## 5. 가중치 (분석 전 동결)

- 곡별 가중치 = `1 / inclusion_prob`(표집 단계에서 기록된 밴드×삼분위 셀 포함확률의 역수).
- 가중/비가중 두 버전을 모두 계산해 병기한다(자문위원 권고 — floor로 인한 소형밴드
  과대표집 정도를 투명하게 드러내기 위함).

## 6. 상관·유의성 판정 (분석 전 동결)

- 지표: 가중 Spearman(가중 순위변환 후 가중 Pearson, `analyze_gems9_n20.py:weighted_spearman`).
- CI: 응답자 단위 재표집(복원추출, 원 응답자 수만큼) → 혼합모형 재적합 → BLUP 재산출 →
  가중 Spearman 재계산을 반복하는 부트스트랩, 반복수 `N_BOOTSTRAP=500`, percentile CI
  (2.5/97.5%). 교과서 Spearman CI 공식은 쓰지 않는다(must-fix, report/04 §2 라운드3).
- 다중비교: GEMS 항목(9개)마다 BH-FDR 별도 적용(report/01과 동일 관례).
- 1차 통과 기준: `|rho| >= 0.4 AND q_bh < 0.05`.
- 밴드 기여도 태깅: 통과 피쳐마다 밴드간분산비중(η², `feature ~ C(band)`의 R²)을 함께
  보고 — 배제하지 않고 표시만 한다.

## 7. 확증(홀드아웃) 판정 기준 (분석 전 동결)

1차 분석이 끝난 뒤에만 `out/gems9_n20_holdout_sealed.csv`를 채점·분석한다. 1차 통과 피쳐
각각에 대해 아래 세 조건을 **모두** 만족해야 "확정 필터 후보"로 승격한다:

1. 부호 일치: 1차 rho와 홀드아웃 rho의 부호가 같다.
2. CI 겹침: 1차 CI와 홀드아웃 CI가 서로 겹친다(어느 한쪽이 완전히 밖에 있지 않다).
3. 실용 효과크기 유지: 홀드아웃 `|rho| >= 0.3`.

**"홀드아웃에서 다시 q<0.05로 유의해야 한다"는 기준은 쓰지 않는다** — 홀드아웃(25곡)은
그 자체로 저검정력이라 이 기준을 쓰면 진짜 효과도 확증에 실패하기 때문이다.

## 8. 이 사전등록 이후 데이터 수집 전 변경 이력

(아직 없음)
