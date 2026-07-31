# audio_feats_revised — 661곡 전수 추출 결과 리포트

`2026-08-01` WSL2(essentia-tensorflow, madmom) 환경에서 9개 스크립트(method-1,2,5,6,7,8,9)를
661곡 전체에 대해 재실행한 결과 요약. method-3(mode)/4(loudness)/10(liveness)/11(speechiness)는
이전 세션에 Windows 네이티브로 이미 검증·산출됨(이 리포트에는 미포함).

**전 스크립트 에러 0건** (661곡 × 7 스크립트, 모두 정상 처리 확인).

## 1. Tempo (method-1, madmom DBNBeatTracker)

| 지표 | 값 |
|---|---|
| bpm_madmom 중앙값 | 171.4 |
| bpm_madmom 범위 | 78.9 ~ 315.8 |
| halftime_flag=True | 31곡 (4.7%) |

- `bpm_autocorr`(librosa 1차 후보)는 이번 세션의 최초 소표본 테스트(4곡)만 남아있고 661곡
  전체 재산출은 하지 않음 — madmom 컬럼(`bpm_madmom` 등)만 이번에 전수 갱신했다. 두 지표를
  전곡 비교하려면 `extract_tempo_librosa.py`도 661곡으로 재실행해야 한다.
- halftime_flag(비트 간격 불안정 — 절반 박자로 잘못 잡았을 가능성) 비율이 4.7%로 낮아
  madmom 추정이 대체로 안정적으로 보인다.

## 2. Key (method-2, K-S 템플릿 vs Essentia KeyExtractor)

| 지표 | 값 |
|---|---|
| mode_ks (K-S) | major 378 / minor 283 |
| mode_essentia | major 394 / minor 267 |
| key_mismatch (진짜 키 불일치) | 255 / 661 (38.6%) |
| mode_only_mismatch (키는 같고 장/단조만 다름) | 33 / 661 (5.0%) |

- 두 알고리즘 간 키 불일치율이 38.6%로 상당히 높다. [[key-profile-bug-status]] 메모에 이미
  기록된 대로 근접조(relative key) 혼동이 상당수를 차지할 것으로 추정되나, 이번 전수
  결과에서는 근접조 여부까지 반영한 뒤의 수치이므로 나머지 불일치는 실제 판정 차이로 봐야
  한다. 두 알고리즘 모두 크로마 기반이라 완전히 독립적인 교차검증은 아니라는 점은 감안할 것.
  50곡 청취 스팟체크가 여전히 인계 대기 상태([[key-profile-bug-status]] 참고).

## 3. Energy/Arousal (method-5, emomusic 회귀 헤드)

| 지표 | 값 |
|---|---|
| arousal_median 중앙값 | 6.83 (1~9 스케일) |
| arousal_median 범위 | 4.37 ~ 7.76 |
| arousal_std 평균 | 0.73 |

- 스케일 상단(9에 가까움)으로 몰려있음 — Bandori 리듬게임 곡 특성상(빠른 템포·전자음
  중심) 전반적으로 각성도가 높게 나온 것은 합리적. 다만 이 모델은 emoMusic/DEAM
  데이터셋(주로 서양 팝/록) 기준으로 학습돼 애니메이션/게임 음악 도메인에 대한 보정은
  없다는 점을 감안해야 한다 — [[acoustic-feature-audit]]에서 이미 지적된 대로 절대값보다는
  **곡 간 상대적 순위**로 활용하는 편이 안전하다.

## 4. Valence (method-6, 동일 emomusic 헤드)

| 지표 | 값 |
|---|---|
| valence_median 중앙값 | 5.79 (1~9 스케일) |
| valence_median 범위 | 4.14 ~ 7.03 |

- 중간값(5) 근처에 밀집 — 곡들이 극단적으로 어둡거나(1) 밝지(9) 않고 중간 톤 위주로
  나온다는 뜻. arousal과 달리 상단으로 쏠리지 않아 감정가(valence)가 리듬게임 장르
  특성보다는 곡별 실제 분위기를 더 잘 구분해주는 것으로 보인다.

## 5. Danceability (method-7, essentia Danceability DFA)

| 지표 | 값 |
|---|---|
| danceability_clf_prob 중앙값 | 1.10 (0~약3 스케일) |
| dfa_alpha 중앙값 | 0.91 |

- 0~3 스케일에서 전체적으로 1.1 근처에 몰려 있어 "중간 정도로 댄서블"한 곡이 대다수 —
  이 알고리즘의 원래 용도(록/팝/EDM 등 장르 구분)에 비해 Bandori 곡들이 장르적으로
  균질하기 때문일 가능성이 있다. `danceability_norm`(표본 내 백분위)이 사실상 곡 간
  상대비교에는 더 유용할 것으로 보임.

## 6. Acousticness (method-8, mood_acoustic 분류기)

| 지표 | 값 |
|---|---|
| acoustic_median 중앙값 | 0.000086 |
| acoustic_median 평균 | 0.016 |
| acoustic_median 최댓값 | 0.916 (`millsage`, `various_artists` 소수 곡) |

- 절대다수 곡이 acoustic 확률 0에 극도로 가깝다 — Bandori 곡 대부분이 전자악기/밴드
  사운드 중심이라는 점과 일치하는 합리적 결과. 밴드별 median이 전부 0에 수렴해 밴드 간
  차이는 거의 없고, 최댓값을 찍은 소수 곡(경음악/포크 편곡 커버 등으로 추정)만 예외적.

## 7. Instrumentalness/Voice (method-9, voice_instrumental 분류기)

| 지표 | 값 |
|---|---|
| voice_median 중앙값 | 0.9992 |
| voice_median 평균 | 0.9938 |
| voice_median 최솟값 | 0.673 |

- 절대다수 곡이 voice 확률 0.99+ — 보컬이 명확한 애니메이션/게임 팝 장르 특성과 일치.
  `instr_stem_ratio`(스템 분리 기반 버전)는 661곡 중 30곡분만 htdemucs 스템이 존재해
  대부분 공란 — 전수 확장하려면 나머지 곡의 보컬 스템 분리가 선행돼야 한다.

## 밴드별 비교 (중앙값 기준, bpm 내림차순)

| band | n | bpm | arousal | valence | dance | acoustic | voice |
|---|---|---|---|---|---|---|---|
| afterglow | 72 | 181.8 | 7.09 | 5.98 | 1.12 | 0.000 | 0.994 |
| roselia | 89 | 181.8 | 6.69 | 5.55 | 1.06 | 0.000 | 1.000 |
| mygo | 44 | 181.8 | 7.01 | 5.36 | 1.10 | 0.000 | 0.996 |
| morfonica | 57 | 176.5 | 6.62 | 5.64 | 1.07 | 0.000 | 0.999 |
| mugendai_mutype | 23 | 176.5 | 6.85 | 5.43 | 1.09 | 0.000 | 0.999 |
| poppin_party | 115 | 176.5 | 6.88 | 6.01 | 1.10 | 0.000 | 1.000 |
| raise_a_suilen | 79 | 171.4 | 6.79 | 5.24 | 1.09 | 0.000 | 0.999 |
| pastel_palettes | 74 | 166.7 | 6.80 | 6.20 | 1.14 | 0.000 | 0.999 |
| hello_happy_world | 72 | 148.2 | 6.86 | 6.27 | 1.18 | 0.000 | 0.999 |
| ave_mujica | 29 | 146.3 | 6.54 | 4.87 | 0.95 | 0.000 | 0.996 |

(millsage/ikka_dumb_rock/various_artists는 표본 수 1~5곡이라 참고용 제외)

- **ave_mujica**가 밴드 중 valence 최저(4.87)·danceability 최저(0.95)로 가장 어둡고
  무거운 톤 — 해당 밴드의 컨셉(다크/멜랑콜리)과 부합하는 결과.
- **hello_happy_world**/**pastel_palettes**가 valence 상위권(6.2~6.3)으로 가장 밝은
  분위기 — 두 밴드 모두 명랑/코미디 컨셉과 일치.
- bpm은 afterglow/roselia/mygo가 공동 최상위(181.8) — 다만 이는 madmom이 배음 옥타브
  오차로 여러 밴드에서 같은 값을 반환했을 가능성도 있어(할프타임/더블타임 오차),
  절대 BPM 비교보다는 참고 수준으로 보는 게 안전하다.

## 종합 메모

- 이번 세션에서 발견한 fork+CUDA 교착 버그, danceability DFA 벡터/스칼라 버그, key
  AudioLoader 버그, voice_instrumental 컬럼 순서 버그, tempo 병합 error 필드 버그 등
  5건은 전수 실행 결과에 실제로 반영돼 있다(버그 수정 후 실행한 결과이므로).
- [[acoustic-feature-audit]]의 기존 교훈대로, energy/valence/danceability 등 사전학습
  분류기 기반 지표는 절대값보다 **곡 간 상대적 순위**로 활용을 권장한다. 이 모델들은
  서양 팝/록 데이터셋으로 학습됐고 Bandori 장르(애니메이션 게임 음악)에 대한 재보정은
  없다.
- 다음 단계 후보: (1) key 불일치 50곡 청취 스팟체크, (2) tempo의 librosa 1차 후보도
  661곡 전수 재산출해 madmom과 비교, (3) instrumentalness stem 버전 확장을 위한 나머지
  보컬 스템 분리.
