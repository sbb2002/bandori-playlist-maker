# Version Log

이 저장소의 버전 이력을 기록한다. `git-rules.md`의 "버전 태깅(Tagging) 및 배포 규칙"에 따라
`epic/*`(Major) / `feature/*`(Minor) / `hotfix/*`(Patch) 브랜치가 `main`에 머지될 때마다
여기에 기록을 남긴다. 자동 태깅 CI(GitHub Actions)는 아직 구축되지 않았으므로, 현재는 git
태그를 수동으로 생성하고 이 로그에 함께 기록한다.

형식: `## vX.Y.Z — YYYY-MM-DD`, 요약, 관련 PR.

---

## v1.8.5 — 2026-07-18

플레이어바 곡 정보(`playbar-info`) 클릭 시, 유튜브 프레임(`.player-card`)과 트랙리스트의
현재 재생 곡 중 지금 화면에서 더 가까운(=보고 있는) 쪽이 아닌 반대쪽으로 스크롤 이동하도록
변경. 기존엔 유튜브 프레임으로만 단방향 이동했다. 별도 토글 상태 없이 매 클릭마다 실제
스크롤 위치(뷰포트 중심과의 거리)를 재계산해 판단(`getViewportCenterDistance`). 기존 클릭
핸들러 하나의 동작을 보정하는 것이라 새 기능(Minor)이 아니라 Patch로 분류.

- 기준 커밋: `b63480c`
- 관련 PR: [#44](https://github.com/sbb2002/bandori-playlist-maker/pull/44)

## v1.8.6 — 2026-07-18

트랙 항목에 우클릭(데스크톱)·길게누름(모바일, 1초) 컨텍스트 메뉴("다음 곡 추가"/"현재 곡
제거")를 추가. 기존 그래프 구간 편집 메뉴(`attachGraphMenu`)와 동일한 타이머·이동취소 패턴을
재사용. 모바일에서 호버가 없어 순서변경·제거 버튼의 존재 자체를 알기 어렵다는 문제의 보조
해결책(버튼 상시노출은 이미 `@media (hover: none)`로 처리돼 있었음 — 중복 규칙 정리도 포함).
기존 트랙 편집 기능(순서변경·제거)의 모바일 접근성을 보완하는 패치라 신규 기능(Minor)이
아니라 Patch로 분류.

- 기준 커밋: `582b021`
- 관련 PR: [#45](https://github.com/sbb2002/bandori-playlist-maker/pull/45)

## v1.8.7 — 2026-07-18

곡 추가 미니 브라우저 검색이 일본어 원문 부분일치에만 의존해, 일본어를 모르는 사용자는 검색이
거의 안 되던 문제를 완화. 서버 기동 시(요청마다 아님) `pykakasi`로 각 곡 제목의 로마자
(`song_romaji`)와 규칙기반 한글 음차(`song_hangul`, 가나 단계에서 직접 변환 — 로마자 경유 시
이중 변환 오차 누적을 피함)를 계산해 `/api/songs` 응답에 추가, 프론트 검색 조건에 포함.
이어서 사용자 피드백으로 외래어(gairaigo) 관용 표기 사전(텔레파시 등 48개), 한자어 한국
한자음 검색(`song_hanja_reading`, `hanja` 라이브러리), 곡별 수동 오버라이드
(`song_alias_overrides.json`, mygo처럼 독자적 읽기를 쓰는 곡 대응)를 추가. 리뷰 중 か행/が행
혼동, 외래어 치환+촉음/장음 조합 크래시, 오버라이드 키가 존재하지 않는 CSV 컬럼(tag)이라
무적용이던 버그를 실제 661곡 데이터로 실행 검증하며 발견·수정. 사용자가 실사용 중 발견한
"ビッグマウス"(빅마우스) 미검색 문제도 반영 — 촉음(っ) 받침이 항상 ㅅ이던 것을 다음 자음
계열(か/が행→ㄱ, ぱ/ば행→ㅂ)에 맞게 일반화하고, 카나 규칙만으론 못 없애는 일본어식 어미모음
잔재는 해당 곡을 외래어 사전에 직접 등록해 보정.
`data/songs_master.csv`(데이터팀 소유)는 건드리지 않음 — 전부 백엔드 인메모리 계산.
"국립국어원 표기법 수준 정밀도가 아니라 들리는 대로 검색되는 실용성"이 목표(완전한 정밀 변환은
사전 인지된 한계). 검색 보조 기능 추가라 신규 기능(Minor)이 아니라 Patch로 분류.

- 기준 커밋: `aad2c0e`
- 관련 PR: [#46](https://github.com/sbb2002/bandori-playlist-maker/pull/46)

## v1.8.8 — 2026-07-18

에너지 그래프 편집기(`syncGraphToParams`)가 백엔드가 실제 선곡에 쓴 `stages[].energy_target`
(비단조 아크 포함)을 무시하고 `start_energy`/`end_energy`만으로 재선형보간해, 피크 등 비단조
아크가 실제 선곡과 무관하게 항상 직선으로 보이던 버그를 수정. `stages`가 있으면 그대로 쓰고,
없을 때만(구버전 백엔드 폴백) 기존 선형보간 유지. 함께, 디테일한 다단계 절대시간 요청("10분에
중간, 20분에 높게, 30분에 최고조...")에서 Groq가 200 응답이면서도 content가 JSON으로 안 풀리는
간헐적 무드 파싱 실패(`MOOD_UNINTERPRETABLE`)가 있어 `GROQ_MOOD_RETRIES`(기본 3)만큼 재호출
후에도 실패하면 기존과 동일하게 폴백하도록 재시도 로직 추가(429/5xx 재시도와는 별개 경로).
기존 동작을 보정하는 버그 수정이라 신규 기능(Minor)이 아니라 Patch로 분류.

- 기준 커밋: `789b039`
- 관련 PR: [#47](https://github.com/sbb2002/bandori-playlist-maker/pull/47)

## v1.9.0 — 2026-07-18

에너지 그래프가 스테이지 중앙을 스플라인으로 부드럽게 잇는 것과 달리, 실제 선곡은 스테이지
경계에서 flat 목표값이 계단식으로 뚝 끊기던 것을 보완 — `continuous_slot_targets()`로 스테이지별
flat 목표를 곡 하나하나 단위로 조각별 선형보간해 경계 근처 곡이 이웃 스테이지 쪽으로 서서히
흘러가게 했다. 검증 중 곡 순서 재배치(`_sequence_by_continuity`, 경계 텐션 정렬)가 강도와 무관한
아웃트로/인트로 신호만으로 애써 매칭해둔 강도 순서를 뒤섞는 것을 발견해, 비용함수에 슬롯목표
이탈 항을 추가하고 2-opt 국소 개선(`_local_refine_order`)으로 탐욕 알고리즘의 후반 슬롯 강제
배치 문제를 보정했다. 선곡 알고리즘 자체에 새 보간 능력을 추가하는 신규 기능이라 Minor로 분류.

- 기준 커밋: `97b4820`
- 관련 PR: [#48](https://github.com/sbb2002/bandori-playlist-maker/pull/48)

---

## Beta (v1.0.0 이전)

정식 버전 태깅 정책을 도입하기 전, 베타 기간 동안의 커밋 단위 변경 이력이다. 원래
`README.md`의 "Version Log" 절에 있던 내용을 이관했다(날짜순 오름차순 — 오래된 순).

- `da4ebdc` — PRD·에이전트 조직도·CLAUDE.md 초기 커밋.
- `c53877a` — 데이터팀 보고서 + .gitignore.
- `920d8f1` — video_id 헬퍼 + Camelot 매핑 + 토큰 게이트 툴.
- `83cdf9a` — songs_master.csv 생성(데이터팀).
- `fc13e2e` — 아키텍처 설계서(스키마 동결).
- `a8b13bc` — 모든 코드를 src/ 하위로 이전 + 폴더별 README 규칙.
- `67a968f` — 파일럿 프로토타입 구현(백엔드 클린아키텍처 + 정적 프론트 + 테스트).
- `e5bd7f9` — OpenRouter 실경로 활성화(.env 로더 + 무료 nemotron 기본).
- `9acae71` — 설정 기능 프로토타입(밴드 필터 + 에너지 단계 직접 지정).
- `aa6ba03` — YouTube 재생 수정 + 에너지 축 교정 + 확률적 선곡 + 텐션 그래프 UI.
- `fa16307` — 선곡 확률 상한 + 텐션 그래프 UX 개선.
- `a16f0b7` — 무드 정확도·연속성 개선(에너지 블렌드 + 급변 방지).
- `fbe91c9` — 2단계 SELECT→SEQUENCE 선곡 엔진 + 백분위 강도.
- `b8fccfa` — R&D 플레이리스트 시퀀싱 전략 연구보고서.
- `9d4f44e` — 에너지 그래프가 요청 해석을 반영.
- `934a5ca` — 전곡 에너지 재추출로 발췌 편향 근본 해결(energy_full).
- `1f8340a` — 시간분절 강도로 '항상 시끄러운' 곡까지 포착.
- `84e8182` — 참고 PDF gitignore.
- `5a0518c` — 곡 경계 텐션 연속성 시퀀싱.
- `8cfe36a` — 프롬프트 밴드명(별명) → 자동 밴드 필터.
- `f35b049` — Original/Cover 곡 종류 필터.
- `7b68366` — 누락 밴드 포함(various_artists·1곡 밴드 eligible 전환).
- `a3ad276` — Stage B 시퀀싱 개선(오프너 인트로 + 경계·하모닉 다목적).
- `fee6b0f` — 핵심 품질 게이트 회귀 테스트 고정.
- `f5a804d` — 비단조 에너지 아크(활동별 LLM 단계 에너지).
- `a9c45de` — YouTube 재생목록 공유 + 프롬프트 밴드 체크박스 동기화 버그 수정.
- `7fa7e9f` — 토큰 초기화 대비 세션 핸드오프 명세서.
- `08b7373` — 핸드오프에 '특정 공연 셋리스트 재현 모드' 미래 기능 추가.
- `0e13f72` — 요청 간 밴드 필터 누적 버그 수정(자동감지분 일회성화).
- `fb6564e` — 플레이리스트 편집 Phase 1: 순서 이동·곡 제거·되돌리기.
- `8488d25` — 순서이동을 '떠 있는 드래그'로 재작성 + 버튼 UI 이미지화 + 텍스트 선택 방지.
- `dcf8ecf` — 플레이리스트 편집 Phase 2: 곡 추가(+) + 미니 밴드/곡 브라우저(/api/songs).
- `e4da922` — 곡 추가 '+'를 트랙 사이 삽입점으로 이동 + 편집 버튼 테마 조화.
- `c211cd1` — 곡 추가 팝업에 밴드 아이콘·순서(song-sorter 동일) + 팝업 스크롤 체이닝 차단.
- `cac8561` — 베타 배포 구성(Render Blueprint + GitHub Pages 워크플로 + 배포 가이드).
- `41c02f5` — 포스트-파일럿 백로그 문서(OAuth 재생목록·공유 팝업·프리셋).
- `99637bd` — umami 방문자 통계 활성화(head 주입).
- `3ff3df8` — 루트 README(프로젝트 소개) 작성.
- `c78275f` — 공유 결과 팝업(B2): 생성 안내 + 공유 URL 복사 + 유튜브 듣기.
- `953b9a9` — LLM 제공자 OpenRouter → Groq 마이그레이션(하루 50회 제한 회피).
- `07a04dd` — Groq 미활성 버그 수정(GROQ_API_KEY 키 이름 오타로 stub 폴백되던 것).
- `6107b54` — 요약 카드를 감성 플레이버 텍스트+해시태그로 개선 + 팬메이드 푸터·우하단 버전 표기·모바일 UI.
- `9734b38` — 프리셋 저장(B3): 좌측 메뉴에서 저장된 플레이리스트 열람·복원·삭제(자동저장·최대 50·Ctrl+Z).
- `c65892d` — Groq RPM 큐제어(토큰버킷) + 동시 처리 200 입장제어(초과 시 안내·개발자 알림) + 파라미터 적극 산출 프롬프트 + 밴드필터 아이콘.

---

## v1.0.0 — 2026-07-13

베타 운영 중이던 저장소의 브랜치·버전 관리 정책(`git-rules.md`)을 정식화하면서 첫 버전을
공표한다. 정책 문서화가 모두 끝난 시점의 `main`을 v1.0.0 기준선으로 삼는다.

- 기준 커밋: `515e9ea` (PR #12 머지 시점의 `main` HEAD)
- 태그: `v1.0.0` (annotated) — 자동 태깅 CI 미구축 상태이므로 수동 생성·푸시함
- 포함 내용: 그 이전까지의 모든 베타 기능/수정 (PR #1 ~ #12, 위 Beta 절 참고)
- 관련 PR: [#11](https://github.com/sbb2002/bandori-playlist-maker/pull/11) `docs: git-rules.md
  브랜치 전략 전면 개편` — **머지 완료(MERGED)**. v1.0.0 공표 확정.

---

## v1.1.0 — 2026-07-13

"내 재생목록에 넣기" — 사용자 본인의 Google 계정에 실제 YouTube 재생목록을 생성한다. 백엔드는
관여하지 않는 순수 클라이언트 사이드 OAuth 토큰 플로우(GIS `initTokenClient`)로, client secret도
refresh token도 두지 않는다. 기존 "유튜브에서 듣기"(익명 `watch_videos` 링크) 버튼을 대체.

- 기준 커밋: `111f5c5`
- 관련 PR: [#15](https://github.com/sbb2002/bandori-playlist-maker/pull/15)

## v1.2.0 — 2026-07-13

Google Search Console 사이트 소유권 확인 파일 추가(OAuth 앱 인증의 승인된 도메인 요건).

- 기준 커밋: `99eda85`
- 관련 PR: [#16](https://github.com/sbb2002/bandori-playlist-maker/pull/16)

## v1.3.0 — 2026-07-13

소유권 확인 파일을 올바른 Google 계정(Cloud 프로젝트 소유 계정)의 것으로 교체.

- 기준 커밋: `c4c690d`
- 관련 PR: [#17](https://github.com/sbb2002/bandori-playlist-maker/pull/17)

## v1.4.0 — 2026-07-13

홈페이지 헤더에 앱 로고를 노출(OAuth 인증의 "브랜딩이 사용자에게 표시되지 않음" 지적 대응).

- 기준 커밋: `2543e43`
- 관련 PR: [#18](https://github.com/sbb2002/bandori-playlist-maker/pull/18)

## v1.5.0 — 2026-07-13

공유 팝업 UI/문구 보강 — 안내문구 2단 구분(공유 링크 / 계정 저장), 우측 상단 동그라미 닫기 버튼,
곡 추가 진행률에 흐르는 사선 패턴 프로그레스 바. 버튼 라벨을 "내 플리 공유하기"로 변경.

- 기준 커밋: `058d287`
- 관련 PR: [#19](https://github.com/sbb2002/bandori-playlist-maker/pull/19)

## v1.6.0 — 2026-07-14

하단 고정 플레이바 신설. 곡명·밴드명·재생시간·순번(n/N) 표시, 이전/재생·일시정지/다음/한 곡 반복
조작, 1초 폴링 진행바(클릭·드래그 seek). 곡명이 길면 한 방향 무한 마퀴. PC·모바일 반응형이며,
터치 환경은 진행바 판정 상자를 키우고 손잡이를 상시 노출한다.

- 기준 커밋: `1a6f79b`
- 관련 PR: [#21](https://github.com/sbb2002/bandori-playlist-maker/pull/21)

## v1.6.1 — 2026-07-14

**계정 저장 실패 시 앱이 영구히 잠기던 버그 수정.** GIS는 팝업 닫힘(`popup_closed`)을 `callback`이
아니라 `error_callback`으로 알리는데 그것을 달지 않아 Promise가 결착되지 않았다 — 인증 심사 중이라
차단 화면을 닫을 수밖에 없는 비테스트 계정 전원이 이 상태에 빠졌다. `error_callback` 추가 +
`try/finally`로 버튼 복구를 보장하고, 계정 저장이 불가능한 예외 상황(심사 중 차단·할당량 소진)에는
익명 임시 재생목록으로 폴백한다.

- 기준 커밋: `a3a1c8f`
- 관련 PR: [#22](https://github.com/sbb2002/bandori-playlist-maker/pull/22)

## v1.6.2 — 2026-07-14

YouTube Data API 할당량 증설 심사(audit)의 필수 증빙 요건에 맞춰 정책 문서를 정비. `privacy.html`에
YouTube API 서비스 이용 고지·YouTube 약관/Google 방침 링크·데이터 삭제 정책을 신설하고, 재생목록
공개 범위 오기("비공개" → 실제는 `unlisted`/일부공개)를 정정. `terms.html`(서비스 약관) 신설.
홈페이지 푸터에 YouTube API 이용 고지(브랜딩)와 방침·약관 링크를 노출.

- 기준 커밋: `8f0fa78`
- 관련 PR: [#23](https://github.com/sbb2002/bandori-playlist-maker/pull/23)

## v1.6.3 — 2026-07-14

모바일 재생바 레이아웃 개선 + 재생 버튼에 어쿠스틱 웨이브 링 애니메이션 추가.

- 기준 커밋: `42c2841`
- 관련 PR: [#26](https://github.com/sbb2002/bandori-playlist-maker/pull/26)

## v1.6.4 — 2026-07-14

> **[백업 버전]** 브랜치 구조를 `data`/`tools`/`research`/`document-archive`로 분리하기 **이전
> 마지막 버전** — `data/`를 포함한 모든 파일이 `main` 하나에 다 있던 마지막 상태다. 분리는
> `v1.7.0`(2026-07-15, `data/`를 `main`에서 제거)부터 시작됐다.

프롬프트(500자)·재생시간(180분/3시간) 입력이 상한을 넘는 순간 값을 되돌리고 안내 문구를 띄우는
프론트 가드레일 추가. 세부설정 그래프로 단계를 직접 지정하는 경로(최대 11단계)는 단계별 상한은
있어도 합산 상한이 없어 3시간을 초과할 수 있었던 백엔드 계산 허점을 넘길 때만 비례 축소하도록
수정. 스텁(오프라인 휴리스틱) 어댑터의 요약 문구에 "(이 문구는 stub입니다.)"를 명시해 실제 LLM
응답과 혼동되지 않도록 함.

- 기준 커밋: `488b8c5`
- 관련 PR: [#27](https://github.com/sbb2002/bandori-playlist-maker/pull/27)

## v1.7.0 — 2026-07-15

`main`에서 `data/` 디렉터리 제거 — 이제 `main`은 앱 소스만 배포한다. 배포된 backend가 런타임에
`data` 브랜치의 `songs_master.csv`를 직접 원격 fetch(신규 `app.repo.remote_source`)해 기동 시 +
주기 리프레시(`DATA_REFRESH_INTERVAL_SEC`, 기본 30분)로 반영한다. `render.yaml`이 `main` push마다
자동 재배포하는데, 지금까지는 신곡이 추가될 때마다 `data` 브랜치를 `main`에 머지해 그 재배포를
트리거해 왔다 — 이제 `data`는 `main`에 아예 병합되지 않으므로 데이터 갱신이 서비스 재기동을
일으키지 않는다(`git-rules.md`의 `data` 브랜치 규칙 갱신). 회귀 가드 테스트(`test_integration.py`)는
실시간 데이터 대신 코드/테스트팀 소유 고정 스냅샷(`src/tests/fixtures/songs_master.csv`)으로
결정론적으로 돈다.

- 기준 커밋: `5e98c39`
- 관련 PR: [#33](https://github.com/sbb2002/bandori-playlist-maker/pull/33)

## v1.8.0 — 2026-07-15

표본 부족 밴드(n<10) 자동 제외 정책(B1)을 폐기 — 표본이 적다는 이유로 곡을 앱에서 아예 빼는 건
부적절하다는 판단(사용자 확정). `src/scripts/data/build_master.py`의 `_MIN_BAND_SAMPLE`을
10→1로 낮춰 실질적으로 항상 eligible이 되게 하고, 신곡 오토로더가 처음으로 실제 반영을
시도하면서 발견한 기존 데이터 불일치(`various_artists`·`ikka_dumb_rock`·`millsage` 3개 밴드,
합 7곡이 정책상 False여야 하는데 실제로는 True로 저장돼 있던 것)를 정책 자체를 바꿔 해소했다.
`CLAUDE.md`·`docs/PRD.md`의 관련 오픈퀘스천도 해결됨으로 갱신. sparse 밴드만 필터링해 긴
재생시간을 요청하는 경우의 선곡 엔진 동작은 별개의 미해결 이슈로 남겨둠.

- 기준 커밋: `d627c28`
- 관련 PR: [#34](https://github.com/sbb2002/bandori-playlist-maker/pull/34)

## v1.8.1 — 2026-07-16

문서 정합성 정리(코드 변경 없음). `git-rules.md`의 `tool/*` 패턴 절을 실제 확정된 단일 `tools`
브랜치(신곡 오토로더가 `feature/song-autoloader`에서 이관·구브랜치 삭제됨) 서술로 교체.
`CLAUDE.md`·`docs/PRD.md`·`docs/architecture.md`에 남아있던 "OpenRouter" 서술을 실제 구현
벤더인 **Groq**로 정정하고, "호스팅 플랫폼 미정" 오픈 퀘스천을 **Resolved**로 표시(프론트
GitHub Pages, 백엔드 Render 무료 플랜 — 이미 `render.yaml`/`pages.yml`로 배포되어 있었음).
`render.yaml`의 시크릿 안내 주석이 여전히 `OPENROUTER_API_KEY`를 언급하던 것을 실제 키 이름인
`GROQ_API_KEY`로 정정. 이 로그의 v1.6.4 항목이 v1.7.0 뒤로 밀려 잘못 붙어있던 인용 줄도
제자리로 복구. (원래 v1.7.1로 태깅했으나, PR #34가 먼저 v1.8.0으로 머지되어 v1.8.1로 재태깅.)

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#35](https://github.com/sbb2002/bandori-playlist-maker/pull/35)

## v1.8.2 — 2026-07-16

`render.yaml`에 `buildFilter.paths`(allowlist: `src/backend/**`, `render.yaml`) 추가. `data/`를
`main`에서 뺀 것과 같은 이유 — `CLAUDE.md`·`git-rules.md`·`docs/`·`versionlog.md`·
`src/frontend/**` 같은 정책 문서·프론트 전용 변경까지 매번 backend를 재배포(콜드스타트 유발)
시키던 것을 막는다. 코드 동작 변경 없음, Render 배포 설정만. (원래 v1.7.2로 태깅했으나, PR #34·
#35가 먼저 v1.8.0·v1.8.1로 머지되어 v1.8.2로 재태깅.)

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#36](https://github.com/sbb2002/bandori-playlist-maker/pull/36)

## v1.8.3 — 2026-07-16

문서 정합성 정리(코드 변경 없음). `research/<주제>` 브랜치를 주제마다 새로 파던 방식을
`data`/`document-archive`/`tools`와 같은 단일 상시 재사용 브랜치 + 폴더 단위 구분으로
전환(`research/mfcc-timbre`·`research/mood-warmth-feature` → 단일 `research` 브랜치,
`topic/mfcc_analysis/`·`topic/mood_warmth/` 폴더 — `data/`와 시각적으로 안 섞이도록
`topic/`로 한 번 더 감쌈). `tools` 브랜치의 신곡 오토로더도 `src/scripts/` →
`auto-loader/`로 재배치(툴 이름이 경로에 드러나도록, 경로 깊이 변경에 따른 REPO_ROOT
하드코딩 8곳 보정 + 유닛테스트 83개로 검증). `data` 브랜치는 `data/` 외 main 스냅샷 잔재를
전부 제거하고 브랜치 전용 `versionlog.md`(신곡 추가=Patch 등 데이터 전용 버전 체계) 신설.
`git-rules.md`에 `research` 절 신규 작성, `tools` 절의 경로 서술 갱신, "브랜치 설명 README"
공통 규칙 신설(`data`·`tools`·`document-archive`·`research` 전부 브랜치 루트 README 필수).
`CLAUDE.md`는 검토 결과 `research/*` 직접 언급이 없어 수정 대상 아님(변경 없음).
추가로 `docs/orgarnization.md`(R&D팀 워크플로가 새 `research` 브랜치 표준구조를 반영하도록,
`data/`가 main에 없다는 사실도 반영)와 `docs/next-steps.md`(Google 심사 대기 항목 외 나머지는
이미 낡은 스냅샷이라 `document-archive`의 `archive/reports/2026-07-14-next-steps-handoff.md`로
이관·삭제)도 함께 정리.

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#37](https://github.com/sbb2002/bandori-playlist-maker/pull/37)

## v1.8.4 — 2026-07-16

우하단에 상시 노출되던 작은 버전 텍스트(커밋 SHA만 표기)를 좌측 햄버거 메뉴 하단으로 옮겨
숨기고, 표기 형식을 `v메인버전 - 커밋SHA`(예: `v1.8.3 - a1b2c3d`)로 바꿨다. GitHub Pages
배포 워크플로(`.github/workflows/pages.yml`)가 빌드시 `git describe --tags --abbrev=0`으로
가져온 최신 태그를 `__VERSION__` 플레이스홀더에 주입(태그 조회를 위해 `checkout`에
`fetch-depth: 0` 추가). 코드 동작(선곡·재생)에는 영향 없음 — 표시용 마이너 수정이라 Patch로
분류.

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: (PR 오픈 후 갱신)
