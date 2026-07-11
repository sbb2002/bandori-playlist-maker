# 전곡(full-track) 지각 에너지 피처 재추출 보고서

작성: 데이터팀(추출) + 부장(복합 확정·통합) · 2026-07-11
근거: `docs/research/2026-07-11-playlist-sequencing-strategy.md` §5(재추출 권고), 사용자 3회 실패 피드백.

## 0. 배경 / 목표
"조용한" 요청에 시끄러운 곡이 새는 근본 원인은 **발췌 구간만 분석된 프록시**(`energy_proxy`·
`acousticness_proxy`)가 조용한 인트로에 속아 실제 시끄러운 곡을 조용하다고 오판하는 것이었다
(処救生·灼熱 Bonfire·ドラマチック·はいよろこんで·黒のバースデイ 등). 기존 피처로는 분리 불가가
확인되어, **로컬 전곡 오디오에서 곡 전체 기준 지각 에너지를 재추출**한다.

## 1. 데이터 / 도구
- 전곡 wav: `bandori-song-sorter/src/content/cluster/audio_full/{band}__{idx:03d}.wav`
  (48kHz mono, 660곡, songs_master.csv와 660/660 매핑). **저작물 → 비커밋.**
- librosa로 추출. 스크립트: `src/scripts/data/extract_full_energy.py`(원시 서브피처),
  `src/scripts/data/build_energy_full.py`(복합·검증·병합).

## 2. 추출 서브피처 (`data/full_audio_features.csv`, 660곡)
곡 전체에서 다음을 **평균과 p90/p95** 두 집계로 산출:
spectral centroid·rolloff·bandwidth·contrast·flatness, zero-crossing rate,
HPSS 타악 에너지 비율(perc), onset strength·onset rate, RMS.
- **raw RMS 절대값은 무용**(파일이 라우드니스 정규화됨 — FIRE BIRD가 최저로 나옴). 단 RMS의
  p90(피크 구간)은 다이나믹 곡 판별에 유효.

## 3. 복합 강도(intensity) 선정
그라운드트루스(조용 14·시끄러움 14·발췌오판 8)로 각 피처의 분리력(AUC·Cohen's d)을 평가하고
복합을 비교했다.
- 데이터팀 자동선정 `mean-5feat(perc,onset,zcr,cen,flat)`은 AUC 0.954지만 **FIRE BIRD(다이나믹
  빌드업)를 pct 0.09로 오판**(조용 처리) → 부적합.
- **부장 확정: `mean-5feat + rms_p90(피크 라우드니스, 가중 ×2)`** — FIRE BIRD를 0.82로 구제하면서
  misjudged party곡을 조용 위로 유지. QUIET-vs-LOUD AUC **0.990**. eligible 풀 백분위로 0~1 정규화 →
  `energy_full`. (수식: 부호정렬 robust z-score의 가중평균 → percentile.)

## 4. 최종 통합 (code팀, `song_repo`)
`energy_full`(전곡)만으로는 **긴 조용 인트로 헤비메탈**(黒のバースデイ=0.136)을 여전히 놓친다.
黒은 어쿠스틱이 아니므로 `acousticness`가 이를 잡는다. 따라서 최종 강도를 **soft-OR로 결합**:

```
intensity = ((energy_full^p + pctl(−acousticness_proxy)^p) / 2)^(1/p),  p=2
```
전곡 에너지가 높거나 비어쿠스틱하면 시끄럽게 본다. (`energy_full` 결측 시 acousticness로 폴백.)

## 5. 검증 (문제곡 강도, 0=조용·1=시끄러움)

| 곡 | 기존 intensity | 신규(energy_full+acou) | 판정 |
|---|---|---|---|
| 処救生 (오판) | 0.064 | **0.048** | 잔여 한계(아래) |
| 灼熱 Bonfire! (오판·party) | 0.088 | **0.299** | 조용 위로 ✓ |
| ドラマチック！アライブ (오판) | 0.134 | **0.654** | ✓ |
| はいよろこんで (오판) | 0.212 | **0.695** | ✓ |
| 黒のバースデイ (오판·헤비메탈) | — | **0.566** | ✓(acousticness가 구제) |
| FIRE BIRD (고에너지) | 0.845 | **0.607** | 유지 ✓ |
| R・I・O・T / EXPOSE | 0.98 | **0.91 / 0.96** | 유지 ✓ |
| 栞 / 過惰幻 (진짜 조용) | 0.005 / 0.004 | **0.002 / 0.008** | ✓ |

**분리도**: QUIET 0.062 · MISJUDGED 0.489 · LOUD 0.795 (기존 0.351 / 0.238 / 0.871 —
misjudged가 조용 **밑→위**로 역전).
**엔드투엔드**(실데이터, 조용 요청 5회·85곡): **오판곡 등장 0건**, 최고강도 0.26.

## 6. 잔여 한계 (정직 보고)
- **処救生(0.048)** 은 전곡 오디오 피처 전부에서 subdued로 측정된다(perc·onset·cen·rms 모두 하위).
  사용자 체감의 "시끄러움"은 보컬 강도·정서적 무게에 가까워 스펙트럼/타악 피처가 못 잡는 영역으로
  판단. 오디오 스칼라 하나로는 해소 불가 — 알려진 잔여 케이스로 남긴다.
- 그라운드트루스가 소규모·수작업(36곡)이라 방향성 근거. 실사용 청취 로그로 확장 권장.
- key 재검증(§5-4)은 미실행(하모닉 정확도 개선 여지, 후속).

## 7b. 시간분절(temporal) 강도 정밀화 (사용자 제안, 2026-07-11 추가)
`energy_full`(단일 스칼라)은 **"평균은 낮지만 한 번도 조용해지지 않는" 곡**(Steer to Utopia,
Re:birth day)을 여전히 낮게 봤다. 사용자 제안대로 **프레임별 강도 시계열**을 추출해 시간분절
통계를 뽑았다(`extract_temporal_intensity.py` → `data/temporal_intensity.csv`, 660곡):
`i_mean·i_std·i_max·i_min·i_start·i_end` (프레임별 강도 = centroid·bandwidth·zcr·flatness·onset·rms의
전역 robust-z 평균).
- 핵심: **`i_min`(가장 조용한 순간)** 이 "절대 조용해지지 않는" 곡을 잡는다 — Steer to Utopia는
  i_min 백분위 0.60(조용 순간 없음), 栞은 0.07(조용 순간 있음). `i_end`는 조용 인트로+시끄러운
  본체(黒)를 잡는다.
- **최종 강도(§4 갱신)**: 서로 다른 곡을 잡는 독립 신호를 soft-OR(power-mean **p=3**)로 결합:
  `intensity = softOR(energy_full, pctl(−acousticness), pctl(i_min), pctl(i_mean), pctl(i_end))`.
  "어느 한 신호라도 시끄럽다면 시끄럽게" — QUIET-vs-LOUD **AUC 0.981**.
- 결과: Steer to Utopia 0.13→**0.48**, Re:birth day →**0.31**, 処救生 0.05→**0.29**(전부 조용 밴드
  밖으로). 栞 0.04·過惰幻 0.05 유지. **실 LLM '조용하고 잔잔한' 3회: 오판곡 0/17, 최고강도 0.28.**
  §6의 処救生 잔여 한계도 시간분절로 해소됨.

## 7. 산출물
- `src/scripts/data/extract_full_energy.py`, `build_energy_full.py`, `extract_temporal_intensity.py`
- `data/full_audio_features.csv`(원시 서브피처), `data/temporal_intensity.csv`(시간분절 통계),
  `data/songs_master.csv`에 `energy_full` + `i_*` 컬럼 병합
- 통합: `src/backend/app/repo/song_repo.py`(intensity = 다신호 soft-OR)
