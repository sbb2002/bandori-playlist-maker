# Version Log

이 저장소의 버전 이력을 기록한다. `git-rules.md`의 "버전 태깅(Tagging) 및 배포 규칙"에 따라
`epic/*`(Major) / `feature/*`(Minor) / `hotfix/*`(Patch) 브랜치가 `main`에 머지될 때마다
여기에 기록을 남긴다. 자동 태깅 CI(GitHub Actions)는 아직 구축되지 않았으므로, 현재는 git
태그를 수동으로 생성하고 이 로그에 함께 기록한다.

**항목은 최신 버전이 위로 오도록 정렬한다.** 작성 형식·분량 기준은 `version-rules.md` 참조.

---

## v1.11.1 — 2026-07-20

장음(ー) 포함 제목의 한글 검색 실패 수정. 원문 음차·한국식 관용 표기 변형을 자동 병기.

- 기준 커밋: `94e1327`
- 관련 PR: [#54](https://github.com/sbb2002/bandori-playlist-maker/pull/54)

## v1.11.0 — 2026-07-19

오토로더 push 직후 즉시 데이터 반영하는 강제 리프레시 엔드포인트 추가(토큰 인증, opt-in).

- 기준 커밋: `c29da40`
- 관련 PR: [#53](https://github.com/sbb2002/bandori-playlist-maker/pull/53)

## v1.10.1 — 2026-07-19

requirements.txt의 존재하지 않는 hanja 버전 핀으로 Render 배포가 막혀있던 것 수정.

- 기준 커밋: `f932ea9`
- 관련 PR: [#52](https://github.com/sbb2002/bandori-playlist-maker/pull/52)

## v1.10.0 — 2026-07-19

무드 파라미터를 4단계로 나눠 순차 LLM 호출하는 실험 어댑터 추가(opt-in, 기본 경로 무영향).

- 기준 커밋: `f537b69`
- 관련 PR: [#51](https://github.com/sbb2002/bandori-playlist-maker/pull/51)

## v1.9.0 — 2026-07-18

스테이지 경계 에너지 계단식 전환을 곡 단위 선형보간으로 완화, 2-opt로 순서 재배치 부작용 보정.

- 기준 커밋: `97b4820`
- 관련 PR: [#48](https://github.com/sbb2002/bandori-playlist-maker/pull/48)

## v1.8.8 — 2026-07-18

비단조 에너지 아크 무시 버그 수정 + Groq 무드 파싱 실패 재시도 로직 추가.

- 기준 커밋: `789b039`
- 관련 PR: [#47](https://github.com/sbb2002/bandori-playlist-maker/pull/47)

## v1.8.7 — 2026-07-18

검색에 로마자·한글 음차·한자음·외래어 사전·곡별 오버라이드 지원 추가(일본어 몰라도 검색 가능).

- 기준 커밋: `aad2c0e`
- 관련 PR: [#46](https://github.com/sbb2002/bandori-playlist-maker/pull/46)

## v1.8.6 — 2026-07-18

트랙 우클릭/길게누름 컨텍스트 메뉴(다음 곡 추가·현재 곡 제거) 추가, 모바일 접근성 보완.

- 기준 커밋: `582b021`
- 관련 PR: [#45](https://github.com/sbb2002/bandori-playlist-maker/pull/45)

## v1.8.5 — 2026-07-18

플레이바 곡정보 클릭 시 반대쪽으로 스크롤하도록 수정(뷰포트 중심 거리 재계산).

- 기준 커밋: `b63480c`
- 관련 PR: [#44](https://github.com/sbb2002/bandori-playlist-maker/pull/44)

## v1.8.4 — 2026-07-16

버전 표기를 우하단 상시노출에서 햄버거 메뉴로 이동, "v메인버전-SHA" 형식으로 변경.

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: (PR 오픈 후 갱신)

## v1.8.3 — 2026-07-16

`research`/`tools`/`data` 브랜치 구조 재편 + `git-rules.md` 문서 정리(코드 변경 없음).

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#37](https://github.com/sbb2002/bandori-playlist-maker/pull/37)

## v1.8.2 — 2026-07-16

`render.yaml`에 `buildFilter` 추가, 문서 변경 시 불필요한 backend 재배포 방지.

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#36](https://github.com/sbb2002/bandori-playlist-maker/pull/36)

## v1.8.1 — 2026-07-16

`git-rules.md`·`CLAUDE.md`·`PRD.md`의 OpenRouter 서술을 실제 벤더 Groq로 정정(문서 정합성).

- 기준 커밋: (PR 오픈 직전 커밋)
- 관련 PR: [#35](https://github.com/sbb2002/bandori-playlist-maker/pull/35)

## v1.8.0 — 2026-07-15

표본 부족 밴드 자동 제외 정책 폐기, 데이터 불일치 3개 밴드 7곡 정상화.

- 기준 커밋: `d627c28`
- 관련 PR: [#34](https://github.com/sbb2002/bandori-playlist-maker/pull/34)

## v1.7.0 — 2026-07-15

`data/`를 `main`에서 분리, backend가 런타임에 `data` 브랜치를 직접 fetch하도록 변경.

- 기준 커밋: `5e98c39`
- 관련 PR: [#33](https://github.com/sbb2002/bandori-playlist-maker/pull/33)

## v1.6.4 — 2026-07-14

프롬프트·재생시간 입력 상한 가드레일 추가, 세부설정 경로 합산 상한 보정.

- 기준 커밋: `488b8c5`
- 관련 PR: [#27](https://github.com/sbb2002/bandori-playlist-maker/pull/27)

## v1.6.3 — 2026-07-14

모바일 재생바 레이아웃 개선 + 재생 버튼 웨이브 링 애니메이션 추가.

- 기준 커밋: `42c2841`
- 관련 PR: [#26](https://github.com/sbb2002/bandori-playlist-maker/pull/26)

## v1.6.2 — 2026-07-14

YouTube API 할당량 심사 대응 — 개인정보처리방침·이용약관 신설, 브랜딩 고지 추가.

- 기준 커밋: `8f0fa78`
- 관련 PR: [#23](https://github.com/sbb2002/bandori-playlist-maker/pull/23)

## v1.6.1 — 2026-07-14

계정 저장 실패 시 앱이 영구 잠기는 버그 수정(GIS `error_callback` 누락).

- 기준 커밋: `a3a1c8f`
- 관련 PR: [#22](https://github.com/sbb2002/bandori-playlist-maker/pull/22)

## v1.6.0 — 2026-07-14

하단 고정 플레이바 신설(재생 조작·진행바·마퀴, PC·모바일 반응형).

- 기준 커밋: `1a6f79b`
- 관련 PR: [#21](https://github.com/sbb2002/bandori-playlist-maker/pull/21)

## v1.5.0 — 2026-07-13

공유 팝업 UI/문구 개선, 곡 추가 진행률 프로그레스 바 추가.

- 기준 커밋: `058d287`
- 관련 PR: [#19](https://github.com/sbb2002/bandori-playlist-maker/pull/19)

## v1.4.0 — 2026-07-13

홈페이지 헤더에 앱 로고 노출(OAuth 브랜딩 요건 대응).

- 기준 커밋: `2543e43`
- 관련 PR: [#18](https://github.com/sbb2002/bandori-playlist-maker/pull/18)

## v1.3.0 — 2026-07-13

Google 소유권 확인 파일을 올바른 계정 것으로 교체.

- 기준 커밋: `c4c690d`
- 관련 PR: [#17](https://github.com/sbb2002/bandori-playlist-maker/pull/17)

## v1.2.0 — 2026-07-13

Google Search Console 소유권 확인 파일 추가.

- 기준 커밋: `99eda85`
- 관련 PR: [#16](https://github.com/sbb2002/bandori-playlist-maker/pull/16)

## v1.1.0 — 2026-07-13

"내 재생목록에 넣기" 추가(클라이언트 사이드 OAuth로 실제 YouTube 재생목록 생성).

- 기준 커밋: `111f5c5`
- 관련 PR: [#15](https://github.com/sbb2002/bandori-playlist-maker/pull/15)

## v1.0.0 — 2026-07-13

`git-rules.md` 브랜치 전략 정식화, 첫 버전 공표(그 이전 베타 기간 전체 포함).

- 기준 커밋: `515e9ea` (PR #12 머지 시점의 `main` HEAD)
- 태그: `v1.0.0` (annotated) — 자동 태깅 CI 미구축 상태이므로 수동 생성·푸시함
- 관련 PR: [#11](https://github.com/sbb2002/bandori-playlist-maker/pull/11)

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
