# 11개 지표 요약 (report_feats.md)

상세는 `method-N-*/out/report/*_findings.md` 참고.

| # | 지표 | 설명 | 결론 |
|---|---|---|---|
| 1 | tempo | 비트 간격으로 잰 BPM | 공식값 94.6% 일치. 5% 배속오차 존재. 순위 신뢰 불가. |
| 2 | key | 크로마로 잰 정확한 조성 | 39.4% 불일치. 근친조 혼동. mode만 활용 권장. |
| 3 | mode | 장조/단조만 추출 | 95.2% 안정. 신뢰 가능. major 우세(56.9%). |
| 4 | loudness | LUFS(음량)+LRA(다이내믹) | 둘 간 약상관(r≈-0.28), 역수 아님. LRA 유망 후보. 청취검증 필요. |
| 5 | energy | 각성도(격함↔차분) | valence 없이 감정 해석 불가. |
| 6 | valence | 정서 밝기(긍정↔부정) | energy 교차 시 90.9% 한 사분면 편중. 변별력 부족. |
| 7 | danceability | 리듬 규칙성(DFA) | 밴드간 차이 작음. tempo·loudness와 무관. lra 결합해야 보조축으로 유의미. |
| 8 | acousticness | 어쿠스틱 확률(proxy) | 95% 0 근접(분포퇴화). 필터 전용, 가중치 부적합. |
| 9 | instrumentalness | 보컬/악기 비중(2종) | voice_median 천장효과로 무용. instr_stem_ratio는 믹싱 밸런스일 뿐 어쿠스틱함과 무관. 이상치 필터용. |
| 10 | liveness | 관중소리+잔향 탐지 | 이스터에그 정답 탐지 실패. rt60 상수화(버그). 폐기 권고. |
| 11 | speechiness | 말하기 vs 노래(2종) | speech_median은 음절밀도 신호로 검증됨. vad_speech_ratio는 도메인 불일치로 오분류 다수. 재정의 보류. |

## 사용가능 / 보류 / 사용불능 분류 (2026-08-02, `data/all_features.csv` 컬럼 기준)

### 사용가능 — 연속변수로 그대로 활용 (상대순위 권장)
- `m4-lufs_integrated`, `m4-lra` (`m4-st_median`/`m4-st_p10`/`m4-st_p90`/`m4-st_std`는 보조)
- `m5-arousal_median` (`m5-arousal_p10`/`m5-arousal_p90`/`m5-arousal_std`는 보조, 절대값 대신 상대순위)
- `m6-valence_median` (`m6-valence_p10`/`m6-valence_p90`/`m6-valence_std`는 보조, 절대값 대신 상대순위)
- `m7-danceability_norm` (`m7-danceability_clf_prob`·`m7-dfa_alpha`는 원자재, norm이 카탈로그 확장에도 안정적)
- `m9-instr_stem_ratio`
- `m11-speech_median` (2026-08-02, method-13 재분류: 청취검증으로 "음절밀도" 신호
  확인됨 + 분포도 종형(skew +0.69, kurtosis 1.04)이라 슬라이더 가중치로도 무리 없음
  — "필터 전용"에서 연속 슬라이더 대상으로 승격. 다만 상/하위 극단값 구간은 여전히
  "속사포 가사"·"낭독조" 같은 좁은 스타일을 가리키므로, 슬라이더와 별개로 프리셋
  필터 용도로도 계속 쓸 수 있음)

**UI 방침(2026-08-02, method-13)**: 위 7개 연속 지표 전부 **백분위 순위(0~100%) 기준으로
슬라이더 통일** 권고. `m7-danceability_norm`은 이미 이 방식으로 만들어짐(왜도/첨도
확인 결과 유일한 완전 uniform). `m4-lra`(skew +2.36)·`m5-arousal_median`(skew -1.76)·
`m4-lufs_integrated`(skew -3.21, kurtosis 18.8)처럼 분포가 치우친 지표를 원값 그대로
슬라이더에 매핑하면 특정 구간에서 후보곡 n이 지나치게 적어질 수 있음 — 백분위 변환으로
방지. `m6-valence_median`·`m11-speech_median`은 이미 종형이라 변환해도 왜곡이
작아 통일해도 손해 없음. 상세: `method-13-multicollinearity/out/report/multicollinearity_findings.md`

### 사용가능 — 필터 전용 (연속 가중치로는 부적합)
- `m8-acoustic_median` (분포 극단 이중화 — 예: `> 0.10` 임계값 필터. 2026-08-02,
  method-13: 8개 연속 지표 중 유일하게 첨도가 지나치게 높아 슬라이더로 조절해도
  체감이 안 됨 — UI는 ALL/NON-ACOUSTIC/ACOUSTIC 3분류 대신 **"어쿠스틱만 찾기"
  ON/OFF 이진 토글**로 단순화 권고. NON-ACOUSTIC이 카탈로그의 94%라 ALL과 거의
  동일해 3분류는 중복 선택지가 됨)
- `m3-mode` (2026-08-02, method-13 재분류: VIF 1.12로 다중공선성은 없으나 major/minor
  이진값이라 연속 가중합 파라미터로 쓰면 곡이 한쪽으로 전부-아니면-전무 식으로 쏠림 —
  "단조 곡만 보기" 같은 필터/태그 전용으로 제한 권고. 상세: `method-13-multicollinearity/out/report/multicollinearity_findings.md`)

### 보류 — 재정의·추가검증 필요
- `m11-vad_speech_ratio` (선율적 보컬을 "music"으로 오분류 → 17곡 0.0 산출, 학습 도메인 불일치)
- `m2-mode_only_mismatch`, `m1-halftime_flag` (method-12에서 옥타브 오차와의 상관 발견, 다만 31곡 소표본이라 확정적 판별 규칙으로 쓰기엔 이름)

### 사용불능
- `m1-bpm_madmom`, `m1-beat_count`, `m1-bpm_autocorr`, `m1-beat_interval_median_sec` (5.4% 옥타브 오차, 절대값·순위 둘 다 신뢰 불가, method-12에서 자기지표 보정도 실패)
- `m2-key_ks`, `m2-key_essentia` (정확 조성, 39.4% 불일치 — 근친조 혼동 심함)
- `m9-voice_median`, `m9-voice_p10`, `m9-voice_p90`, `m9-voice_std` (천장효과로 std=0.023, 변별력 상실)
- `m10-crowd_median`, `m10-crowd_p10`, `m10-crowd_p90`, `m10-crowd_std`, `m10-rt60_est_sec`, `m10-noise_floor_db` (분포퇴화 + rt60 전곡 5.0초 상수화)
