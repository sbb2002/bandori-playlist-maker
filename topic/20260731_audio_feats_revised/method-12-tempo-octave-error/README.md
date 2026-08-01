# method-12-tempo-octave-error

## 목적
method-1-tempo에서 Bestdori 공식 BPM과 대조해 확인된 **옥타브 오차(배속 2x / 반절 0.5x /
그 외 비정수배)** 31곡과, 8% 오차 이내로 정확히 일치한 542곡을 두 그룹으로 나눠,
method-2~11에서 산출한 지표들 중 두 그룹을 뚜렷이 구분하는 지표가 있는지 탐색한다.

새로운 오디오 추출은 하지 않는다 — `data/all_features.csv`(method-1~11 병합본)와
`method-1-tempo/out/csv/tempo_bestdori_comparison.csv`(정답 대조 결과)만 재사용하는
순수 사후분석(post-hoc) 폴더.

## 그룹 정의
- **correct(정답군)**: `ratio(=bpm_madmom/official_bpm)`가 0.92~1.08 이내 — 542곡
- **octave_error(오류군)**: 그 외 31곡 — half(0.5x) 14곡, double(2x) 13곡, 기타(2/3·3/2배 등) 4곡

Bestdori에 매칭 안 된 163곡(주로 커버곡)은 정답 자체가 없어 이 분석에서 제외.

## 방법
- 수치형 지표: Mann-Whitney U 검정(비모수, 소표본 강건) + rank-biserial 효과크기
- 불리언 플래그: Fisher's exact test
- 다중비교 보정: 검정한 지표 수가 많아(수십 개) 단순 p<0.05만으로는 우연한 유의성이
  섞일 수 있음 — Bonferroni 보정 기준도 함께 표기해 신중하게 해석한다.

## 산출물
- `out/csv/octave_group_comparison.csv` — 지표별 그룹 통계·검정 결과
- `out/fig/octave_group_boxplots.png` — 상위 유의 지표 박스플롯
- `out/report/octave_findings.md` — 해석
