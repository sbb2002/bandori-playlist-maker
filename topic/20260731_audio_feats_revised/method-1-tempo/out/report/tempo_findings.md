# Tempo (method-1, madmom DBNBeatTracker) — 상세 리포트

> 요약은 상위 `../../REPORT.md` §1 참고. 이 파일은 tempo 관련 전체 내용(컬럼 설명·
> Bestdori 대조·밴드별 불일치율·연구 아이디어)을 담는다.

## 컬럼 설명

`method-1-tempo/out/csv/tempo_raw.csv`:

| 컬럼 | 의미 |
|---|---|
| `bpm_autocorr` | librosa 온셋 자기상관 기반 1차 후보 BPM (이번 세션엔 661곡 재산출 안 함, 소표본만 존재) |
| `bpm_madmom` | madmom `DBNBeatTracker`가 잡은 비트 간격의 **중앙값**으로 환산한 BPM — 이번 리포트의 대표 tempo 값 |
| `beat_count` | 곡 전체에서 검출된 비트 개수 |
| `beat_interval_median_sec` | 연속 비트 간 간격의 중앙값(초) — `60/이 값` = `bpm_madmom` |
| `halftime_flag` | 비트 간격의 `IQR/median > 0.3`이면 True. **곡 내에서 비트 간격이 들쭉날쭉했는지**만 재는 지표이지, 옥타브(배속/반절) 오차를 탐지하는 지표가 아니다 — 곡 전체가 처음부터 끝까지 일관되게 2배로 잘못 잡히면 간격 자체는 균일해 이 플래그로는 걸리지 않는다(아래 Bestdori 대조에서 실오차 31곡 중 65%를 놓침) |
| `duration_sec` / `extract_sec` / `error` | 곡 길이(초) / 추출 소요시간(초) / 실패 시 예외 메시지(정상 시 빈 값) |

`method-1-tempo/out/csv/tempo_bestdori_comparison.csv` (Bestdori 공식 BPM 대조용, 추가 컬럼만):

| 컬럼 | 의미 |
|---|---|
| `official_bpm` | Bestdori에서 크롤링한 공식 BPM(정답 근사치) |
| `ratio` | `bpm_madmom / official_bpm` — 1에 가까우면 일치, 약 0.5면 반절 오차, 약 2면 배속 오차 |
| `octave_class` | `ratio`가 0.42~0.58이면 `half(0.5x)`, 1.85~2.15면 `double(2x)`, 그 외는 공란(2/3배 등 비정수배 오차 포함) |

## 기본 통계

| 지표 | 값 |
|---|---|
| bpm_madmom 중앙값 | 171.4 |
| bpm_madmom 범위 | 78.9 ~ 315.8 |
| halftime_flag=True | 31곡 (4.7%) |

- `bpm_autocorr`(librosa 1차 후보)는 이번 세션의 최초 소표본 테스트(4곡)만 남아있고 661곡
  전체 재산출은 하지 않음 — madmom 컬럼(`bpm_madmom` 등)만 이번에 전수 갱신했다. 두 지표를
  전곡 비교하려면 `extract_tempo_librosa.py`도 661곡으로 재실행해야 한다.
- halftime_flag(비트 간격 불안정 — 절반 박자로 잘못 잡았을 가능성) 비율이 4.7%로 낮아
  madmom 추정이 대체로 안정적으로 보인다 ~~고 평가했으나, 아래 Bestdori 대조 결과 이 판단은
  과신이었다~~.

## ⚠️ Bestdori 공식 BPM 대조 결과 (2026-08-01 추가 검증)

이전 세션(`topic/20260720_audio_feats_analysis/out/bestdori_bpm.csv`)에 크롤링해둔 Bestdori
공식 BPM과 `bpm_madmom`을 idx 기준으로 대조했다(스크립트: `method-1-tempo/src/build_bestdori_comparison.py`,
산출물: `method-1-tempo/out/csv/tempo_bestdori_*`, `method-1-tempo/out/report/tempo_bestdori_*`, `method-1-tempo/out/fig/tempo_bestdori_*`).

| 지표 | 값 |
|---|---|
| Bestdori 매칭 곡수 | 573 / 661 (나머지 88곡은 커버곡 등 미매칭) |
| 8% 오차 이내 일치 | 542곡 (94.6%) |
| **옥타브 오차 (배속/반절)** | **31곡 (5.4%)** — 배속(2x) 13곡, 반절(0.5x) 14곡, 그 외 4곡 |
| 불일치 곡 중 halftime_flag=True로 이미 잡힌 비율 | 11/31 (35%) |

- **halftime_flag는 옥타브 오차 탐지 신뢰도가 낮다** — 불일치 31곡의 65%는 플래그 없이
  조용히 섞여 있었다. "halftime_flag 4.7%라 안정적"이라는 위 평가는 재고가 필요하다.
- 이번 리포트의 "전체/밴드별 tempo 상·하위 10곡" 표(`method-1-tempo/out/report/tempo_report.md`)에
  등장한 여러 상위권 곡(idx 146/565/572/71 등)이 그대로 이 불일치 목록과 겹친다 — 즉
  **해당 표의 상위권 다수가 실제로는 배속 오차로 부풀려진 순위**였다. official_bpm으로
  보정 전까지는 tempo 절대값·상하위 순위를 그대로 신뢰하지 않는다.
- 다음 단계 후보로 취급: (1) 옥타브 오차 31곡을 Bestdori 값으로 보정한 `bpm_final` 컬럼
  산출, (2) 나머지 88곡(미매칭)의 옥타브 오차 여부는 청취로만 확인 가능.

**밴드별 불일치율** (Bestdori 매칭 5곡 이상 밴드만, 불일치율 내림차순 — 전체 표는
`method-1-tempo/out/report/tempo_bestdori_mismatch.md` 참고):

| band | n | 불일치 | 불일치율 |
|---|---|---|---|
| ave_mujica | 9 | 2 | 22.2% |
| mygo | 31 | 4 | 12.9% |
| raise_a_suilen | 72 | 6 | 8.3% |
| hello_happy_world | 71 | 5 | 7.0% |
| poppin_party | 107 | 5 | 4.7% |
| roselia | 87 | 4 | 4.6% |
| pastel_palettes | 74 | 3 | 4.1% |
| morfonica | 52 | 1 | 1.9% |
| afterglow | 70 | 1 | 1.4% |

- 밴드(장르 성향 대리지표)별 편차가 뚜렷하다 — ave_mujica/mygo/raise_a_suilen이 상위권.
  다만 ave_mujica는 n=9(불일치 2곡)로 표본이 작아 22.2%는 통계적으로 불안정하니 참고만 할 것.
- 반절 오차(0.5x, 14곡)는 대부분 **원곡 BPM 187~260대 고속곡**, 배속 오차(2x, 13곡)는
  **원곡 BPM 75~135대 저속곡**에서 발생 — madmom이 자기 탐지범위(55~320)의 중간대
  (150~200bpm)로 쏠리는 경향과 일치한다.

**연구자 제안 아이디어(미검증, 참고용)**: energy/valence/danceability 등 시계열 기반
피처는 곡을 시간 구간으로 나눠 측정하므로 구간별 요약통계(`_median/_p10/_p90/_std`)가
이미 산출돼 있다. 이 요약통계들을 입력으로 삼아 **0.5배/1배/2배 옥타브 클래스를 예측하는
간단한 분류 모델**을 만들 수 있지 않겠냐는 제안이 나왔다. 검증 시 혼동행렬을 반드시 볼
것, 그리고 위 표에 나온 소수의 2/3배 등 정수배 아닌 오차는 이 3클래스 틀에 들어가지 않으므로
별도 취급이 필요하다는 점도 함께 언급됨. 아이디어 자체의 타당성(애초에 저 요약통계들이
옥타브 오차와 실제 상관이 있을지)은 미검증 — 착수 전에 소표본으로 상관관계부터 확인 필요.

## 관련 산출물

- `out/csv/tempo_raw.csv` — 661곡 원시 tempo 값
- `out/report/tempo_report.md` — 전체/밴드별 상·하위 10곡 표 (⚠️ 옥타브 오차 미보정 상태)
- `out/csv/tempo_bestdori_comparison.csv` — Bestdori 공식 BPM 대조 전체 데이터(573행)
- `out/report/tempo_bestdori_mismatch.md` — 불일치 31곡 + 밴드별 불일치율 표
- `out/fig/tempo_bestdori_scatter.png` — madmom vs Bestdori 산점도
- `out/fig/tempo_violin.png` / `out/fig/tempo_violin.html` — 전체·밴드별 tempo 분포 바이올린 플롯
- `src/build_bestdori_comparison.py` / `src/build_tempo_report.py` / `src/plot_tempo_violin.py` — 위 산출물 생성 스크립트
