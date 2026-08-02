# method-13-multicollinearity

## 목적
`report_feats.md`에서 "사용가능"으로 분류한 지표들끼리 상관·다중공선성(VIF)을 확인한다.
새로운 오디오 추출은 하지 않는다 — `data/all_features.csv`만 재사용하는 순수 사후분석
(post-hoc) 폴더 (method-12와 동일한 성격).

## 대상 컬럼
- 연속(상대순위 활용): `m4-lufs_integrated`, `m4-lra`, `m5-arousal_median`,
  `m6-valence_median`, `m7-danceability_norm`, `m9-instr_stem_ratio`
- 필터 전용이지만 값 자체는 연속이라 상관 계산에는 포함: `m8-acoustic_median`,
  `m11-speech_median`
- 범주형: `m3-mode`(major=1/minor=0으로 인코딩해 참고용으로만 포함, VIF 본 계산에서는
  제외 — 이진 변수의 VIF는 회귀 기반 해석이 어색해 상관행렬에만 참고 표시)

## 방법
- Pearson 상관행렬 + Spearman 상관행렬(둘 다 계산, 분포 왜곡된 지표(acoustic_median)
  대응)
- VIF(Variance Inflation Factor): 각 지표를 나머지 지표들로 선형회귀했을 때의
  R²로부터 `VIF = 1/(1-R²)` 직접 계산(statsmodels 미설치라 numpy 최소자승으로 구현)
- 통상 기준: VIF>5 주의, VIF>10 심각한 다중공선성

## 산출물
- `out/csv/correlation_pearson.csv`, `out/csv/correlation_spearman.csv`
- `out/csv/vif.csv`
- `out/fig/correlation_heatmap.png`
- `out/report/multicollinearity_findings.md`
