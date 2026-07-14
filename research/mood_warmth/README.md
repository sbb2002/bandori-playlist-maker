# 무드 "따뜻함/가련·애절(pathos)" 파라미터 연구 (research/mood-warmth-feature)

## 배경
`esora no clover`(morfonica) 청취 인상 검증 과정에서, 현재 선곡 파라미터(brightness=mode_score,
energy)만으로는 "애절하지만 위로되지 않는" vs "따뜻하게 위로되는" 차이를 구분 못한다는 가설이 나옴.
대조곡(Sonorous, 天球のMúsica)은 brightness·energy 자체가 이미 달라 통제된 대조쌍이 아니었음 —
새 파라미터가 정말 필요한지 판단하려면 esora와 **음향적으로 유사한 곡들 사이에서 청취 인상이 갈리는지**
먼저 봐야 함.

## 1단계 — 유사곡 라벨링 (완료)
- `song_features_with_proxies.csv`(bandori-song-sorter, 660곡) 기준, 대표성 있는 6개 feature로
  z-score 유클리드 거리 계산: `harmonic_ratio`·`contrast`(스펙트럼형태군 대표)·`flux`·`rms`(고유기여
  상위, VIF 검증됨)·`mode_score`(valence)·`voiced_frac_mix`.
- esora 최근접 30곡 → `candidates_worksheet.csv`, 사용자가 esora 유사도(1=유사~5=비유사) 라벨링.
  rank19(idx 97)는 rank9(idx 91)와 동일곡(영문/일어명 중복)이라 제외 → **유효 n=29**.
  (중복곡 데이터 정리는 별도 feature/data 작업 필요 — 일어명 기준 유지.)
- **결과**: 기존 6 feature 전체 회귀 R²=0.228 — 지각의 77%가 미설명. 유일 유의 `voiced_frac_mix`
  (r=−0.383, p=.041). 거리(dist) 자체는 rating과 무상관(r≈0) — 기존 feature 공간이 이 지각을 못 잡음.
- 평점 1(가장 유사) 곡들의 공통 청취노트 = "오페라풍 절규/고음" → 보컬 발성 가설 수립.

## 2단계 — 보컬 발성 feature 검증 (완료, 2026-07-15)

### 방법
- 레퍼런스 5편(`ref/`) 근거: Li 2026(보컬/반주 분리 필수), Kato&Ito 2013(jitter/shimmer/HNR),
  Nussbaum 2022(F0 통계), Armitage 2024(mode×timbre 불일치).
- 32곡(라벨 29 + 앵커: esora 208 / Sonorous 196 / 天球のMúsica 78)을 Demucs htdemucs
  two-stems 분리(`separate_vocals.py`, 32/32 성공) 후 보컬 스템 전곡에서 8개 발성 feature 추출
  (`extract_vocal_features.py` → `vocal_features.csv`): jitter_local·shimmer_local·hnr_mean(Praat),
  f0_median/range/std(semitone, pyin), vocal_ratio(보컬RMS/믹스RMS), vocal_centroid.
- 파생 1개: incongruence = |z(mode_score)−z(centroid)| (660 코퍼스 z 기준).
- 사전 등록 판정 기준(`analyze_warmth.py` → `analysis_results.md`):
  채택 후보 = |Spearman ρ|≥0.5(p<.05) AND 편상관(mode_score·voiced_frac_mix 통제) |ρ|≥0.4;
  시사적 = 0.37≤|ρ|<0.5; 그 외 기각. BH-FDR q 병기, 위계 회귀 ΔR²(1개씩).
- 환경: conda env `warmth`(py3.11, demucs 4.1.0, torch 2.13 CPU, parselmouth 0.4.7, librosa 0.11).
  베이스라인 R²=0.2283 재현 일치(무결성 확인). 추출 결정성 검증 통과(재추출 diff 0).

### 결과 — 채택 후보 0개, 시사적 1개

| feature | Spearman ρ | p | q(BH) | 편상관 ρ | ΔR² | 판정 |
|---|---|---|---|---|---|---|
| **f0_range_st** | **−0.441** | .017 | .149 | −0.301 | +0.078 | **시사적** |
| f0_std_st | −0.291 | .126 | .566 | −0.186 | +0.093 | 기각 (Pearson r=−0.426였으나 주 분석은 Spearman) |
| jitter_local | −0.191 | .320 | .721 | −0.124 | +0.016 | 기각 |
| vocal_centroid | +0.204 | .287 | .721 | +0.080 | +0.066 | 기각 |
| incongruence | −0.158 | .414 | .746 | −0.102 | +0.012 | 기각 |
| f0_median_st | +0.111 | .567 | .851 | +0.018 | 0.000 | 기각 |
| vocal_ratio | +0.062 | .749 | .901 | +0.025 | +0.041 | 기각 |
| shimmer_local | −0.049 | .801 | .901 | −0.032 | +0.003 | 기각 |
| hnr_mean | −0.007 | .971 | .971 | +0.049 | +0.041 | 기각 |

### 해석
1. **f0_range_st(보컬 F0 음역폭)만 시사적** — 방향(음역 넓을수록 esora 유사)이 "오페라풍 고음 절규"
   가설과 일치. 단 FDR 미생존(q=.149)·편상관 기준 미달(−0.301)로 단독 채택 불가, 표본 확대 재검 대상.
2. **H1(jitter/shimmer/HNR) 기각의 원인 추정 — 범위 제한**: 이 코퍼스는 전부 클린 보컬
   (jitter 0.98~1.97%)로, Kato&Ito가 다룬 극단 발성(그로울 9~28%) 대비 분산이 좁아 신호가 묻힘.
   전곡 집계 노이즈·Demucs 아티팩트도 가세.
3. **H2(vocal_ratio) 기각 — 역설적 발견**: 정밀 보컬 비중은 무상관(ρ=.06)인데 기존
   voiced_frac_mix는 유의(−0.383)였다 → voiced_frac_mix가 재던 것은 "보컬 크기"가 아니라
   **믹스의 유성/지속(legato) 텍스처**일 가능성. 기존 지표 재해석 필요.
4. **앵커 정합성 — f0_range 단독으론 부족**: esora(79pct)와 天球(86pct)가 둘 다 높음 →
   이 지표는 "드라마틱한 보컬"은 잡지만 가련(esora) vs 강렬(天球)은 못 가름. 둘을 가르는 건
   mode_score(단조 vs 장조)와 vocal_ratio(28 vs 86pct) → **가련함 = 단일 축이 아니라
   조합(단조 × 넓은 F0 음역 × 억제된 보컬/어쿠스틱 텍스처)일 가능성**. n=29로는 조합 가설 검정 불가.

### 다음 단계 옵션 (미결정)
- (a) **표본 확대**: 전곡 660 분리+추출로 f0_range_st 재검(사전등록 경로). CPU ~11–22h,
  GPU torch 설치 시(RTX 4080) 대폭 단축 가능.
- (b) **라벨 축 개선**: 현 rating은 "esora 유사성"이라 밝기·가련함 혼재 — 차기 라벨링은
  "가련/애절함" 직접 축으로 수집해 지각 타깃을 깨끗하게.
- (c) **조합 파라미터 실용 노선**: 신규 축은 f0_range(드라마틱 보컬) 하나만 추가하고,
  "가련함"은 선곡 로직에서 (brightness 낮음 × f0_range 높음) 조합으로 표현 — LLM 스키마 변경 최소.
- 검증 완료 시 보고서 .md는 `document-archive`의 `archive/research/`로 별도 커밋.

### 산출물
- `separate_vocals.py` / `extract_vocal_features.py` / `analyze_warmth.py` (env `warmth`로 실행)
- `vocal_features.csv`(32행) · `analysis_results.md`(전체 통계표·앵커표) · `fig/*.png`(상위 3 산점도)
- `stems/`(보컬 분리 wav, gitignore — 재생성 가능) · `separate_log.txt` · `install_log.txt`
