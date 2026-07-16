# 데이터팀 팀장 보고서 — 소스 데이터 실측 검증 및 사원 티켓 설계

- 일자: 2026-07-10
- 작성: 데이터팀 팀장 (opus) / 정리: 부장
- 검수 결과: **승인** (R6 경로 위반 없음 — 파일 쓰기 0건, 산출물 보고서만)

## ① 목표

bandori-song-sorter 소스 데이터 3종 실측 검증, 정책 확정, 사원 티켓 3건 설계 (PRD §6·§7·§9).

## ② 실측 결과 (전부 실측, 추정 없음)

| 항목 | 결과 |
|---|---|
| 행 수 | 3파일 모두 660 (PASS) |
| 조인 | **전역 `idx`(0–659)가 정답 조인 키.** idx 조인 시 660행 완전 매칭, 불일치 0. audio_map.json은 배열 위치 == idx |
| band+song 조인 | **부적합** — 동일 제목 별개 레코딩 2쌍 존재: raise_a_suilen/R・I・O・T (idx 501, 525), roselia/Neo-Aspect (idx 570, 588). 진짜 중복 아님 |
| null/중복 | 전 컬럼 null 0, url·idx 중복 0 (PASS) |
| key | 정확히 24종 (12maj+12min), 표기 `^[A-G]#?(maj\|min)$`, 샤프만 사용. 최소 표본 D#min 6곡 |
| url | 660행 전부 `https://youtu.be/<11자 video_id>`, 예외 0 (PASS) |
| 밴드 분포 | 13그룹: poppin_party 115 ~ ikka_dumb_rock/millsage 각 1. **n<10 = 3그룹(various_artists 5, ikka_dumb_rock 1, millsage 1), 합 7곡** |
| 수치 범위 | energy_proxy: -6.585~7.750 (unbounded) / tempo_excerpt: 86.13~172.27 BPM / mode_score: -0.374~0.431 / **json.energy: 0–1 정규화 완료** |

**엔진 권장**: 에너지 축 1차 소스는 json.energy(0–1 즉시 사용 가능), energy_proxy·tempo는 정규화 후 보조 — 코드설계팀과 스키마 협의 필요.

## ③ 미완료 (정직 보고)

- key 음정 정확도 검증 — 원본 오디오 필요, 데이터팀 스코프 밖 (R&D팀/오디오 기기 필요. PRD §7 "부정확 가능성 감안" 유지)
- 기존 피처의 무드 매칭 적합성 (PRD §9) — R&D팀 온디맨드 대상

## ④ 정책 (부장 승인 사항)

- **B1. 표본 부족 밴드: `n≥10` 채택 (부장 잠정 승인, 사용자 최종 결재 대기)**
  - n≥10 적용 시 10밴드/653곡 유지, 손실 7곡(1.06%)
  - 구현: 전역 풀 660곡 유지 + `eligible_band` 불리언 플래그. 밴드 필터·다양성 제약에서만 3그룹 제외. various_artists는 밴드 아님(컴필레이션 버킷)
- **B2. data/ 복사 정책**: 원본 3파일 무가공 복사 + idx 조인 canonical `data/songs_master.csv` 생성 (컬럼: idx, band, song, url, video_id, key, camelot, tempo_excerpt, energy_proxy, mode_score, acousticness_proxy, instrumentalness_proxy, bpm, energy, shape, eligible_band)
- **B3. .gitignore**: 오디오 확장자·audio_cache 차단 — 부장이 적용 완료 (2026-07-10)

## ⑤ 사원 티켓 명세

**의존성**: 티켓2·3 완전 독립(병렬 가능) → 완료 후 티켓1 (songs_master.csv가 두 모듈을 import).

### 티켓1 — 데이터 복사·조인·정합성 검증
- 산출: `data/` 원본 3파일 + `data/songs_master.csv`, `scripts/data/build_master.py`
- 검증(assert): 660행 일치 / idx unique·결측 0 / idx 조인 band·song 불일치 0 / title 충돌 2쌍이 idx로 별개 유지 / eligible_band n≥10 규칙(7곡 False)

### 티켓2 — video_id 추출 헬퍼
- 산출: `scripts/data/video_id.py` (`extract_video_id(url) -> str`), 단위 테스트
- 검증: 660 url 전부 11자 id 추출 / 비정상 포맷 명시적 처리 / 테스트 통과

### 티켓3 — key→Camelot 매핑
- 산출: `scripts/data/camelot.py` (매핑 dict + `to_camelot(key)` + `adjacent(camelot)`), 단위 테스트
- 검증: 24종 1:1 매핑 / 미지 key 예외 / 인접 규칙(같은 번호 A↔B, ±1 동일 문자) / 660행 매핑 누락 0

## ⑥ 다음 단계

1. ~~부장: .gitignore 적용~~ (완료), n≥10 사용자 최종 결재
2. 티켓2·3 병렬 스폰 → 검수 → 티켓1
3. key 신뢰도·피처 적합성은 R&D팀 온디맨드로 이관
4. 코드설계팀과 에너지 축 스키마 협의
