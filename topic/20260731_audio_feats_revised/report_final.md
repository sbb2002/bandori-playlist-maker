# 연구 최종 결론 (report_final.md)

11개 지표 전수 산출(`report_feats.md`) → 사용가능/보류/사용불능 분류 →
다중공선성 검증(`method-13-multicollinearity`) → 분포별 UI 사용방안까지, 이 연구의
목표(선곡 파라미터로 쓸 유의미한 지표 선정)를 달성했다. 상세는
`method-13-multicollinearity/out/report/multicollinearity_findings.md` 참고.

## 최종 채택 파라미터 (9개)

| 컬럼 | 용도 | UI |
|---|---|---|
| `m4-lufs_integrated` | 라우드니스 | 백분위 슬라이더(0~100%) |
| `m4-lra` | 다이내믹 범위 | 백분위 슬라이더 |
| `m5-arousal_median` | 각성도 | 백분위 슬라이더 |
| `m6-valence_median` | 정서 밝기 | 백분위 슬라이더 |
| `m7-danceability_norm` | 리듬감 | 백분위 슬라이더(이미 이 방식으로 산출됨) |
| `m9-instr_stem_ratio` | 보컬/악기 비중 | 백분위 슬라이더 |
| `m11-speech_median` | 음절밀도 | 백분위 슬라이더 |
| `m8-acoustic_median` | 어쿠스틱 여부 | ON/OFF 토글 (`> 0.10` 임계값 필터) |
| `m3-mode` | 장조/단조 | 필터/태그 (예: "단조만 보기") |

## 판단 근거 요약

- **VIF 전부 < 5**(최댓값 3.32, `m5-arousal_median`) — 9개 지표 모두 통계적으로
  안심하고 동시 사용 가능, 다중공선성으로 제외해야 할 지표 없음.
- **연속 7개는 백분위 순위(percentile rank)로 통일**: 대부분 종형/균등분포지만
  `m4-lra`(skew +2.36)·`m5-arousal_median`(skew -1.76)·`m4-lufs_integrated`
  (skew -3.21, kurtosis 18.8)는 원값 슬라이더로 노출 시 특정 구간 후보곡이
  급감할 수 있어 백분위 변환 필요.
- **`m8-acoustic_median`은 슬라이더 부적합**: 첨도 48로 극단적 이중분포(94%가 0
  근접) — ON/OFF 토글로 단순화.
- **`m3-mode`는 통계적으로 독립적(VIF 1.12)이지만 이진값이라 가중합 슬라이더에
  부적합** — 필터/태그로만 사용.

## 제외/보류 지표

- **사용불능**: tempo(`m1-*`, 옥타브 오차), key(`m2-key_ks`/`m2-key_essentia`, 39.4%
  불일치), `m9-voice_*`(천장효과), liveness(`m10-*`, 분포퇴화·rt60 상수화).
- **보류**: `m11-vad_speech_ratio`(도메인 불일치 오분류), `m2-mode_only_mismatch`·
  `m1-halftime_flag`(옥타브 오차 상관 있으나 소표본).

## 다음 단계(연구 범위 밖, 구현 인계 사항)

1. 백분위 변환 파이프라인 구현(카탈로그 확장 시 재계산 필요, `danceability_norm`
   선례 참고).
2. `m8-acoustic_median` 임계값(0.10)·`m3-mode` 필터 UI 프로토타입 검증.
3. key 불일치 50곡 청취 스팟체크 등 기존 인계 사항은 본 연구 범위 밖이라 별도 진행.
