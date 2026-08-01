# data/all_features.csv — 컬럼 메타데이터

`src/build_merged_data.py`가 method-1~11의 `out/csv/*_raw.csv`를 `idx` 기준으로 outer
merge해 만든 파일(736행 x 111열). `idx`를 제외한 모든 컬럼은 어느 method에서 왔는지
한눈에 알 수 있도록 **`m<N>-<원래컬럼명>`** 접두사를 붙였다(N=1~11, 예: `bpm_madmom` →
`m1-bpm_madmom`). band/song/duration_sec/error/extract_sec/n_patches처럼 여러 method에
동일한 이름으로 존재하는 컬럼도 값이 method마다 미세하게 다르거나(duration_sec) 실패
원인이 다를 수 있어(error) 병합하지 않고 `m<N>-band`처럼 각각 보존했다. 대표로 노출하는
`band`/`song`(접두사 없음)은 method-1-tempo(736곡 전수) 값을 canonical로 채택한 것이다.

각 지표의 상세 해석·검증 결과·주의사항은 `report_feats.md`(11개 지표 요약) 및
`method-N-*/out/report/*_findings.md`(지표별 상세) 참고 — 이 문서는 **컬럼 의미**만 정리한다.

## 공통 식별자

| 컬럼 | 의미 |
|---|---|
| `idx` | 곡 고유 식별자(전역, `songs_master.csv` 기준) |
| `band` / `song` | 밴드명 / 곡명 (method-1-tempo 값을 canonical로 채택, 접두사 없음) |
| `m<N>-band` / `m<N>-song` / `m<N>-duration_sec` | method별로 독립 산출된 동일 정보 — 값 대조·오류 추적용으로 보존 |
| `m<N>-error` | 해당 method 추출 실패 시 예외 메시지(정상 시 빈 값). method별로 원인이 다르므로 병합하지 않음 |
| `m<N>-extract_sec` | 해당 method 추출 소요시간(초) — 일부 method만 존재 |
| `m<N>-n_patches` | 시계열 기반 method(m5/m6/m8/m9/m10)의 패치(윈도우) 개수 — 진단용 |

## m1 — tempo

| 컬럼 | 의미 |
|---|---|
| `m1-bpm_autocorr` | librosa 온셋 자기상관 기반 1차 후보 BPM(소표본만 존재, 661곡 재산출 안 됨) |
| `m1-bpm_madmom` | madmom DBNBeatTracker 비트 간격 중앙값 기반 BPM — 대표 tempo 값 |
| `m1-beat_count` | 검출된 비트 개수 |
| `m1-beat_interval_median_sec` | 비트 간 간격의 중앙값(초), `60/이 값 = bpm_madmom` |
| `m1-halftime_flag` | 비트 간격의 `IQR/median > 0.3`이면 True. 곡 내 비트 간격 불안정 여부만 표시 — **옥타브(배속/반절) 오차 탐지 지표 아님**(실오차 31곡 중 65%를 놓침, `tempo_findings.md` 참고) |

## m2 — key

| 컬럼 | 의미 |
|---|---|
| `m2-key_ks` / `m2-mode_ks` | K-S 템플릿 매칭 다수결 최종 조성 / 장·단조 |
| `m2-key_ks_confidence` | 다수결 1위 조합의 지속시간 비율(0~1), 1에 가까울수록 곡 전체가 한 조성 |
| `m2-modulation_flag` | 2위 후보 비율 0.25 이상이면 True — 곡 중간 전조 가능성 신호 |
| `m2-key_essentia` / `m2-mode_essentia` | Essentia KeyExtractor 추정 조성/장단조 — 교차검증용 |
| `m2-key_mismatch` | `key_ks != key_essentia`(근접조 미보정 단순 불일치 — 실제보다 부풀려질 수 있음) |
| `m2-mode_only_mismatch` | key는 같은데 mode만 다른 경우 True — 청취 스팟체크 우선 대상 |

## m3 — mode

| 컬럼 | 의미 |
|---|---|
| `m3-mode` | `m2-key_ks`의 `mode_ks`를 그대로 재노출한 값(major/minor) — 오디오 재분석 없는 부산물 컬럼 |

## m4 — loudness

| 컬럼 | 의미 |
|---|---|
| `m4-lufs_integrated` | 통합 라우드니스(LUFS, pyloudnorm) — 곡 전체의 지각적 음량 대표값 |
| `m4-lra` | EBU R128 Loudness Range ≈ short-term loudness의 p95-p10 — 곡 내 다이내믹(강약) 기복 폭 |
| `m4-st_median` / `m4-st_p10` / `m4-st_p90` / `m4-st_std` | 3초 윈도우 short-term loudness의 요약통계 — std는 lra와 함께 다이내믹 변화의 교차검증 신호 |
| `m4-mastering_flag` | lufs_integrated가 스트리밍 표준 타깃(-14/-16/-23 LUFS 등) 근처에 몰려있는지 표시 |

## m5 — energy (arousal)

| 컬럼 | 의미 |
|---|---|
| `m5-arousal_median` / `m5-arousal_p10` / `m5-arousal_p90` / `m5-arousal_std` | emoMusic/DEAM 계열 회귀모델이 패치별로 추정한 각성도(격함↔차분함)의 요약통계. **valence 없이 단독으로 감정의 긍/부정을 정의할 수 없음** |

## m6 — valence

| 컬럼 | 의미 |
|---|---|
| `m6-valence_median` / `m6-valence_p10` / `m6-valence_p90` / `m6-valence_std` | 동일 계열 모델이 추정한 정서적 밝기(긍정↔부정)의 요약통계. `mode_score`(m3 계열)를 valence 대용으로 쓰지 않는다는 게 원 설계 원칙 |

## m7 — danceability

| 컬럼 | 의미 |
|---|---|
| `m7-dfa_alpha` | Essentia `Danceability` 알고리즘의 원시 DFA 지수(α) — RMS 에너지 시계열의 프랙탈 규칙성. **낮을수록** 리듬이 규칙적("danceable") |
| `m7-danceability_norm` | `1 - percentile_rank(dfa_alpha)` 카탈로그 내 상대 정규화(0~1, 높을수록 규칙적) — 리포트의 대표값 |
| `m7-dfa_alpha_native` | librosa/nolds 기반 네이티브 DFA 참고 대조값(선택 산출) |
| `m7-danceability_clf_prob` | 사전학습 danceability 분류기 확률(ML 대체 proxy, 참고용) |

## m8 — acousticness

| 컬럼 | 의미 |
|---|---|
| `m8-acoustic_median` / `m8-acoustic_p10` / `m8-acoustic_p90` / `m8-acoustic_std` | Essentia `mood_acoustic` 분류기가 패치별로 추정한 어쿠스틱(생악기) 확률의 요약통계. 95%가 0~0.05에 몰리는 분포 퇴화 있음 — 연속 가중치가 아닌 필터 용도로만 사용 권장 |

## m9 — instrumentalness

| 컬럼 | 의미 |
|---|---|
| `m9-instr_stem_ratio` | `1 - (보컬스템 에너지 / 전체 에너지)` — "보컬 없음"이 아니라 **보컬 대비 악기의 믹스 에너지 비중**을 재는 지표 |
| `m9-voice_median` / `m9-voice_p10` / `m9-voice_p90` / `m9-voice_std` | Essentia `voice_instrumental` 분류기의 보컬 존재 확률 요약통계. 거의 전곡이 0.99~1.0에 몰리는 천장효과로 변별력 낮음 |

## m10 — liveness

| 컬럼 | 의미 |
|---|---|
| `m10-crowd_median` / `m10-crowd_p10` / `m10-crowd_p90` / `m10-crowd_std` | PANNs가 추정한 Crowd/Applause/Cheering(관중 소음) 확률의 요약통계. 실제 라이브 이스터에그 곡도 탐지 못 함(검증 실패, `liveness_findings.md` 참고) |
| `m10-noise_floor_db` | 트랙 전체 노이즈플로어(dB, 하위 percentile 기준) |
| `m10-rt60_est_sec` | 잔향 꼬리 길이 추정(초) — **전곡 5.0으로 상수화된 버그성 결함, 사실상 무의미** |

## m11 — speechiness

| 컬럼 | 의미 |
|---|---|
| `m11-speech_median` / `m11-speech_p10` / `m11-speech_p90` / `m11-speech_std` | 보컬 스템의 Scheirer-Slaney 4Hz 변조 에너지 비율 요약통계 — 음절 밀도/단조로움(말하듯 vs 선율적) 신호로 검증됨 |
| `m11-n_frames` | speech 변조 에너지 계산에 쓰인 프레임 수 |
| `m11-vad_speech_ratio` | inaSpeechSegmenter가 "speech"로 라벨링한 세그먼트 길이 ÷ 전체 길이. 방송음성 vs 배경음악 분류기의 도메인 불일치로 노래 전체가 "music"으로 오분류되는 사례 다수(0.0값 17곡) — 재정의 필요 |
| `m11-vad_n_frames` | VAD 세그먼트 개수 |
| `m11-vad_error` | VAD 단계 실패 시 예외 메시지 |
