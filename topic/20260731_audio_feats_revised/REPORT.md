# audio_feats_revised — 736곡 전수 추출 결과 리포트

`2026-08-01` 661곡으로 시작한 이 연구는 이후 신규 75곡(주로 mugendai_mutype 커버곡)을
검증·반영해 **736곡**으로 확장됐다. idx 충돌 구조 문제를 발견해 `idx`(전역 유일
synthetic key)와 `file_idx`(오디오 파일명 번호, 밴드 내에서만 유일)를 분리하는 영구
구조 개선을 거쳤다(`CONVENTIONS.md` "idx와 file_idx" 절 참고). 로컬 GPU(RTX 4080
Super)가 CPU 전용 torch 때문에 방치돼 있던 것도 이번에 발견해 CUDA 빌드로 교체했다.

**11개 method 전부 736곡 기준 전수 산출 완료, 에러 0건**(liveness의 PANNs 102곡
실패, loudness의 예전 idx=3 중복 1건 등 개별 이슈는 각 섹션 참고).

각 method의 상세 리포트(컬럼 설명·플롯·밴드별 분석·캐비아트)는 해당
`method-N-*/out/*_findings.md`에 있다 — 이 파일은 요약 + 링크만 담는다.

## 1. Tempo (method-1, madmom DBNBeatTracker)

> 상세: `method-1-tempo/out/tempo_findings.md`

| 지표 | 값 |
|---|---|
| bpm_madmom 중앙값 | 171.4 |
| bpm_madmom 범위 | 78.9 ~ 315.8 |
| halftime_flag=True | 34곡 (4.6%, ⚠️ 옥타브 오차 탐지용으로는 신뢰 낮음) |
| Bestdori 공식 BPM 대조 | 매칭 573곡(신규곡은 공식 게임 미수록이라 매칭 불가) 중 94.6% 일치, 5.4% 옥타브 오차 |

- mugendai_mutype이 23→77곡으로 늘며 밴드 중앙값이 176.5→153.8로 크게 이동 —
  소표본 순위가 불안정했음을 보여줌.
- ⚠️ tempo 절대값·상하위 순위는 옥타브 오차 보정 전까지 신뢰하지 말 것.

## 2. Key (method-2, K-S 템플릿 vs Essentia KeyExtractor)

> 상세: `method-2-key/out/key_findings.md`

| 지표 | 값 |
|---|---|
| mode_ks (K-S) | major 419 / minor 317 |
| key_mismatch (정확한 조성 불일치) | 290/736 (39.4%) |
| **mode만(장/단조만) 일치율** | **73.9%** — key 절대값보다 훨씬 안정적 |

- Bestdori API에 애초에 key 필드가 없음을 직접 확인 — 공식 자료 대조 불가능.
- 베이스 스템 검증(736곡: 48%/42% 일치)·모드 스케일 확장 실험(736곡) 모두 완료 —
  roselia에서 Phrygian 사례 확인, morfonica "A minor 쏠림"이 실제로는 Phrygian
  색채일 가능성 제기(휴리스틱 템플릿이라 참고용).
- ⚠️ 50곡 청취 스팟체크 여전히 인계 대기([[key-profile-bug-status]]).

## 3. Mode (method-3, key_ks에서 파생)

> 상세: `method-3-mode/out/mode_findings.md`

| 지표 | 값 |
|---|---|
| major / minor | 419곡(56.9%) / 317곡(43.1%) |

- major 쏠림: afterglow, hello_happy_world, pastel_palettes(밝은 컨셉과 부합)
- minor 쏠림: roselia(61.5%), raise_a_suilen(63.3%), morfonica(62.1%), ave_mujica(65.5%)
  — 단, 이 밴드들은 method-2에서 mode 신뢰도 자체가 하위권(63~77%)으로 확인된
  곳이라 재검증 필요.

## 4. Loudness (method-4, LUFS/LRA)

> 상세: `method-4-loudness/out/loudness_findings.md`

| 지표 | 값 |
|---|---|
| LUFS 통합 라우드니스 평균 | -11.03 (std 1.95) |
| 범위 | -26.77 ~ -7.39 |
| LRA(동적범위) 평균 | 4.09 |

- ave_mujica가 가장 크고(−9.82) 다이나믹(LRA 6.90), mugendai_mutype이 가장 작음(−13.04).
- ⚠️ idx=3(afterglow "I knew it!") 예전부터 있던 중복행 1건 미해결로 남아있음(무해).
- mastering_flag 전부 0 — 스트리밍 정규화 미적용 원본 마스터링 상태.

## 5. Energy/Arousal (method-5, emomusic 회귀 헤드)

> 상세: `method-5-energy/out/energy_findings.md`

| 지표 | 값 |
|---|---|
| arousal_median 중앙값 | 6.80 (1~9 스케일) |
| 범위 | 4.03 ~ 7.76 |

- 밴드 간 편차가 좁음(6.54~7.09) — afterglow 최고, ave_mujica/mugendai_mutype 최저.
- 서양 팝/록 데이터셋 학습 모델이라 절대값보다 상대순위 권장([[acoustic-feature-audit]]).

## 6. Valence (method-6, 동일 emomusic 헤드)

> 상세: `method-6-valence/out/valence_findings.md`

| 지표 | 값 |
|---|---|
| valence_median 중앙값 | 5.79 (1~9 스케일) |

- hello_happy_world(6.26)·pastel_palettes(6.20) 최상위, ave_mujica(4.87) 최하위 —
  661곡 때 관찰된 밴드 컨셉과의 부합 패턴이 736곡에서도 그대로 유지됨.

## 7. Danceability (method-7, essentia DFA + 분류기)

> 상세: `method-7-danceability/out/danceability_findings.md`

| 지표 | 값 |
|---|---|
| danceability_clf_prob 중앙값 | 1.10 |
| dfa_alpha 평균 | 0.91 |

- hello_happy_world 최고(norm 0.74), ave_mujica 최저(norm 0.10).
- `danceability_norm`(표본 내 상대순위)이 절대값보다 유용 — 카탈로그 확장에도 의미 안정적.

## 8. Acousticness (method-8, mood_acoustic 분류기)

> 상세: `method-8-acousticness/out/acousticness_findings.md`

| 지표 | 값 |
|---|---|
| acoustic_median 중앙값 | 0.0001 |
| acoustic_median 최댓값 | ~0.99 |

- **극단적 이중분포**: 절대다수(스튜디오 밴드곡)는 0 근처, 커버/"Acoustic Ver." 태그
  곡만 0.4~0.99 — 모델이 어쿠스틱 신호 자체는 정확히 감지하지만 중간대가 텅 비어있음.
- 연속 가중치로는 부적절, **필터 전용**(예: acoustic_median > 0.10) 활용 권장.

## 9. Instrumentalness/Voice (method-9, stem 에너지비 + essentia 분류기)

> 상세: `method-9-instrumentalness/out/instrumentalness_findings.md`

| 지표 | 값 |
|---|---|
| instr_stem_ratio 중앙값 | 0.71 (범위 0.33~0.91) |
| voice_median 중앙값 | 0.9993 |

- 두 지표는 정의상 반대 방향(스피어만 ρ=-0.254, 방향은 정상, 크기는 `voice_median`의
  천장효과 탓에 약함 — voice_median std=0.023로 변별력 상실).
- **instr_stem_ratio를 주지표로 사용 권장** — morfonica(0.82, 악기多) vs
  raise_a_suilen(0.68, 보컬多) 등 밴드 간 실질적 차이를 보여줌.

## 10. Liveness (method-10, PANNs Crowd/Applause/Cheering)

> 상세: `method-10-liveness/out/liveness_findings.md`

| 지표 | 값 |
|---|---|
| crowd_median 범위 | 0.000427 ~ 0.001721 (634/736, PANNs 102곡 실패) |
| rt60_est_sec | **736곡 전부 정확히 5.0초로 클리핑 — 사실상 무의미** |

- 변동계수 0.20으로 심한 분포퇴화 확인 — 스튜디오 녹음 위주 카탈로그 특성상 예상된 결과.
- **이 지표 세트는 현재 카탈로그(라이브 녹음 거의 없음)에서는 실용적 가치가 낮다**는
  비판적 결론 — 상위 곡들도 갱보컬/함성 이펙트 오탐 의심.

## 11. Speechiness (method-11, 4Hz 변조에너지 + VAD)

> 상세: `method-11-speechiness/out/speechiness_findings.md`

| 지표 | 값 |
|---|---|
| speech_median(4Hz 변조에너지) 중앙값 | 0.066 (범위 0.022~0.145) |
| vad_speech_ratio(inaSpeechSegmenter) 평균 | 0.168 (범위 0~0.637) |

- ⚠️ `vad_speech_ratio`는 처음에 `Segmenter(detect_gender=True)` 기본값 버그로
  736곡 전부 0.0으로 잘못 산출됐던 걸 발견·수정(`detect_gender=False`)한 뒤 재산출한 값.
- 두 지표 스피어만 상관 0.204(약하지만 유의) — 서로 다른 메커니즘(미시적 변조 리듬 vs
  거시적 발화구간 비율)을 재는 만큼 완전히 일치하지 않는 게 정상.
- afterglow·mygo가 vad_speech_ratio 상위(보컬 비중 높음), pastel_palettes·raise_a_suilen 하위.

## 밴드별 종합 비교 (736곡, bpm 내림차순, 표본 10곡 이상만)

| band | n | bpm | arousal | valence | dance | instr_stem | lufs | speech |
|---|---|---|---|---|---|---|---|---|
| afterglow | 72 | 181.8 | 7.09 | 5.98 | 1.12 | 0.71 | -10.60 | 0.070 |
| roselia | 91 | 181.8 | 6.70 | 5.55 | 1.06 | 0.69 | -10.73 | 0.058 |
| morfonica | 58 | 176.5 | 6.63 | 5.64 | 1.07 | 0.82 | -10.73 | 0.060 |
| poppin_party | 116 | 174.0 | 6.87 | 6.01 | 1.10 | 0.70 | -10.81 | 0.058 |
| mygo | 60 | 174.0 | 6.89 | 5.42 | 1.10 | 0.79 | -9.33 | 0.069 |
| raise_a_suilen | 79 | 171.4 | 6.79 | 5.24 | 1.09 | 0.68 | -10.40 | 0.069 |
| pastel_palettes | 74 | 166.7 | 6.80 | 6.20 | 1.14 | 0.71 | -10.90 | 0.069 |
| mugendai_mutype | 77 | 153.8 | 6.54 | 5.67 | 1.13 | 0.71 | -12.61 | 0.078 |
| hello_happy_world | 72 | 148.2 | 6.86 | 6.27 | 1.18 | 0.70 | -11.21 | 0.078 |
| ave_mujica | 29 | 146.3 | 6.54 | 4.87 | 0.95 | 0.72 | -9.22 | 0.045 |

(acoustic_median·voice_median은 전 밴드 거의 0/1에 수렴해 표에서 생략 —
각 method 섹션 참고)

- **ave_mujica**가 valence 최저(4.87)·danceability 최저(0.95)로 가장 어둡고 무거운
  톤 — 밴드 컨셉과 부합.
- **hello_happy_world/pastel_palettes**가 valence 상위권(6.2~6.3)으로 가장 밝음.
- **mugendai_mutype**이 신규 편입 후 bpm 최하위권(153.8)·loudness 최저(-12.61)로
  이동 — 표본 확장으로 밴드 특성 추정이 크게 바뀐 대표 사례.
- bpm 최상위 afterglow/roselia(181.8 동률)는 madmom 배음 옥타브 오차 가능성 있어
  참고 수준으로만 볼 것.

## 종합 메모

- 이번 세션에서 발견·수정한 버그: tempo librosa idx append 버그(중복 421건 → 복구),
  instrumentalness_stem 동일 유형 버그(에이전트 자체 복구), **speechiness VAD의
  라벨 매칭 버그**(`detect_gender=True` 기본값 때문에 결과가 항상 0.0 고정 →
  `detect_gender=False`로 수정), idx 전역 충돌 구조 문제(`file_idx` 분리로 영구 해결).
- [[acoustic-feature-audit]]의 기존 교훈대로, energy/valence/danceability 등 사전학습
  분류기 기반 지표는 절대값보다 **곡 간 상대적 순위**로 활용 권장.
- acousticness·liveness는 분포퇴화가 심해 연속 가중치보다 필터/보조 지표로만 활용 권장.
- 다음 단계 후보: (1) key 불일치 50곡 청취 스팟체크(여전히 최우선), (2) liveness
  PANNs 실패 102곡 원인 조사, (3) loudness idx=3 중복 정리, (4) roselia/morfonica
  전체 표본으로 모드 스케일 확장 재검증.
