# 데이터팀 작업 완료 보고 — 티켓1 최종 검수 및 코드설계팀 인계

- 일자: 2026-07-10
- 검수: 데이터팀 팀장(R2 최종 승인) / 정리: 부장
- 판정: **티켓1 승인 — 데이터팀 전체 작업(티켓1·2·3 + 토큰 게이트) 종결**

## 티켓1 검수 경과

1. 사원(sonnet) 1차 완료 → **부장 반려 1회**: cp949 콘솔에서 요약 출력 중 U+30FB(가운뎃점)
   UnicodeEncodeError 크래시 (사원 환경은 UTF-8 stdout이라 미검출).
2. 사원 재작업: `_make_stdout_safe()`(stdout/stderr UTF-8 reconfigure, try/except 방어) 추가.
   산출 CSV 4개 md5 대조로 바이트 동일 입증. 부장 재실행 exit 0 재현.
3. 팀장 최종 검수 승인 — 주요 실측:
   - 조인 로직 코드 직독: 전역 idx 기반, band+song 조인 없음 (band/song 비교는 검증 assert 전용)
   - eligible_band: Counter 집계 + n≥10 규칙 기반 계산 (하드코딩 아님), 660행 전수 재검증 위반 0
   - title 충돌 4행(idx 501/525 R・I・O・T, 570/588 Neo-Aspect) 별개 레코딩 보존 — 1차 검증 원본
     실측치와 값 일치로 조인 무결성(컬럼 밀림 없음) 교차 확인
   - 16컬럼 B2 명세 일치, 복사본 3파일 원본과 md5 동일
   - video_id 660개 11자·고유 660, camelot 전부 유효, eligible_band False 정확히 7행

## 산출물 (커밋 대상)

- `data/songs_master.csv` — 단일 진실 소스 (660행 × 16컬럼)
- `data/songs_full.csv`, `data/song_features_with_proxies.csv`, `data/audio_map.json` — 원본 무가공 복사
- `scripts/data/build_master.py` — 멱등 빌드 스크립트 (전체 assert 내장)

## 코드설계팀 인계 노트 (팀장 최종본)

1. **단일 진실 소스**: `data/songs_master.csv`. 선곡 엔진은 이 파일만 읽는다.
   **식별 키는 `idx`(또는 `video_id`) — `band+song` 사용 금지** (동일 제목 별개 레코딩 2쌍).
2. **에너지 축**: 1차 소스는 `energy` 컬럼(0–1 정규화 완료, 즉시 사용 가능).
   `energy_proxy`(unbounded -6.58~7.75)·`tempo_excerpt`(BPM 86~172 원시)는 엔진 측 정규화 필수.
3. **하모닉 믹싱**: `camelot` 컬럼 + `scripts/data/camelot.py`의 `adjacent()`/`is_adjacent()` 사용.
   **호환 판정은 `a == b or is_adjacent(a, b)`** — is_adjacent는 동일 코드를 인접으로 안 침.
4. **`eligible_band`는 CSV상 문자열 "True"/"False"** — 로드 시 불리언 파싱 필요.
   밴드 필터·다양성 제약에서 False 7행 자동 제외 (B1 정책 n≥10, 653곡 유지).
5. **key 신뢰도 미검증**(PRD §7) — 하모닉 추천이 이따금 부자연스러울 수 있음을 엔진/UX에서 감안.
6. **video_id 포맷 확장 동결** — 신규 포맷은 데이터 실측 시에만.
7. 부장 잔여 액션: ~~.gitignore 적용~~(완료), data/·scripts/data/ 커밋(이 보고서와 함께).

## 다음 단계

코드설계팀 팀장(opus) 스폰 — 클린 아키텍처 경계 설계(PRD §8) + 구현 티켓 분할.
