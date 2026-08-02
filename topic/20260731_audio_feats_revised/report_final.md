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

## 앱 조절부(UI/LLM) 적용 방향 — 번외 논의 요약 (2026-08-02)

실제 구현(`bandori-playlist-maker`)은 두 경로로 파라미터를 채운다: ① LLM에게
"~~한 느낌의 플레이리스트" 자연어 프롬프트를 보내 파라미터를 자동 설정 → songs
pool 생성, ② 사용자가 세부설정에서 시간구간 그래프 UI로 직접 조정(energy는
이미 이 방식). 이번 연구의 분류가 두 경로 모두에 그대로 재사용 가능한 공통
스펙 역할을 한다.

- **LLM 자동 경로**: 연속 7개는 이미 백분위(0~100) 스케일로 통일해뒀으므로 LLM이
  "밝고 신나게=valence 80, arousal 70"처럼 사람이 이해하는 척도 그대로 값을
  채우면 된다 — LUFS dB·LRA 같은 원 단위를 LLM이 직접 추론하게 하는 것보다
  안정적. `m8-acoustic_median`(ON/OFF)·`m3-mode`(필터)는 프롬프트에 "어쿠스틱
  버전으로"·"슬픈 단조 곡 위주로" 같은 명시적 언급이 있을 때만 LLM이 건드리고,
  기본값은 OFF/전체로 둔다.
- **세부설정(수동) UI**: 기존 시간구간 그래프 UI를 그대로 재사용하되,
  `m5-arousal_median`↔`m6-valence_median`만 **2D 맵**(정서 원형/circumplex
  모델)으로 승격해 사용자가 시간에 따른 궤적(경로)을 하나의 평면 위에서
  직관적으로 지정하게 한다 — 이 둘은 상관 r=+0.417로 약하게 동행하고 개념적으로도
  하나의 정서 축 쌍이라 별개의 1D 그래프 두 개보다 자연스럽다. 나머지 5개
  (`m4-lufs_integrated`, `m4-lra`, `m7-danceability_norm`, `m9-instr_stem_ratio`,
  `m11-speech_median`)는 기존 시간구간 그래프 UI를 그대로 쓰되 "고급 설정"
  섹션에 접어둬 조절 부담을 줄인다.

## 다음 단계(연구 범위 밖, 구현 인계 사항)

1. 백분위 변환 파이프라인 구현(카탈로그 확장 시 재계산 필요, `danceability_norm`
   선례 참고).
2. `m8-acoustic_median` 임계값(0.10)·`m3-mode` 필터 UI 프로토타입 검증.
3. arousal-valence 2D 맵 궤적 UI 프로토타입 및 LLM 프롬프트→백분위 파라미터
   매핑 규칙 설계(번외 논의, 별도 구현 트랙).
4. key 불일치 50곡 청취 스팟체크 등 기존 인계 사항은 본 연구 범위 밖이라 별도 진행.
