# method-1-tempo/out — 컬럼 메타데이터

## tempo_raw.csv

두 스크립트가 idx 기준으로 컬럼만 병합해 채운다 — `extract_tempo_librosa.py`(1차 후보,
네이티브)와 `extract_tempo_madmom.py`(정제, WSL2). 저장 위치: `../csv/tempo_raw.csv`

| 컬럼 | 의미 |
|---|---|
| `idx` / `band` / `song` / `duration_sec` | 곡 식별자·밴드·곡명·길이(초) |
| `bpm_autocorr` | librosa 온셋 자기상관 기반 1차 후보 BPM. 이번 세션엔 661곡 재산출 안 함 — 최초 소표본(4곡) 값만 존재 |
| `bpm_madmom` | madmom `DBNBeatTracker`가 잡은 비트 간격의 **중앙값**으로 환산한 BPM(`60/beat_interval_median_sec`) — 이번 리포트의 대표 tempo 값 |
| `beat_count` | 곡 전체에서 검출된 비트 개수 |
| `beat_interval_median_sec` | 연속 비트 간 간격의 중앙값(초) |
| `halftime_flag` | 비트 간격의 `IQR/median > 0.3`이면 True. **곡 내에서 비트 간격이 들쭉날쭉했는지**만 재는 지표 — 옥타브(배속/반절) 오차 탐지 지표가 아니다. 곡 전체가 처음부터 끝까지 일관되게 2배로 잘못 잡히면 간격 자체는 균일해 이 플래그로는 안 걸린다(Bestdori 대조에서 실오차 31곡 중 65%를 놓침, 상세는 `tempo_findings.md`) |
| `extract_sec` | 추출 소요시간(초) |
| `error` | 실패 시 예외 메시지(정상 시 빈 값) |

## tempo_bestdori_comparison.csv

`build_bestdori_comparison.py`가 `../csv/tempo_raw.csv`와 `topic/20260720_audio_feats_analysis/out/bestdori_bpm.csv`
(이전 세션에 Bestdori에서 크롤링한 공식 BPM)를 idx로 조인한 결과. `../csv/tempo_raw.csv`의 전
컬럼 + 아래 컬럼을 포함(573행 = Bestdori 매칭된 곡만, 커버곡 등 88곡은 미매칭이라 제외). 저장 위치: `../csv/tempo_bestdori_comparison.csv`

| 컬럼 | 의미 |
|---|---|
| `official_bpm` | Bestdori 공식 BPM(정답 근사치) |
| `ratio` | `bpm_madmom / official_bpm` — 1에 가까우면 일치, 약 0.5면 반절 오차, 약 2면 배속 오차 |
| `octave_class` | `ratio` 0.42~0.58 → `half(0.5x)`, 1.85~2.15 → `double(2x)`, 그 외는 공란(2/3배 등 비정수배 오차 포함) |

## tempo_report.md / tempo_bestdori_mismatch.md

CSV가 아닌 마크다운 리포트(컬럼 없음) — 각각 전체/밴드별 상하위 10곡 표, 옥타브 불일치
31곡 + 밴드별 불일치율 표. ⚠️ `tempo_report.md`는 옥타브 오차 보정 전 값이므로 상위권
다수가 실제로는 배속 오차로 부풀려진 순위임에 주의(`tempo_findings.md` 참고).
