# 🎧 setlist-maker

> 한 문장이면 됩니다. 기분·상황을 말하면 **밴드리(BanG Dream!) 곡으로 긴 재생 흐름**을 만들어 드려요.

자연어 요청 한 문장을 **LLM으로 무드·에너지 의도**로 해석하고, **하모닉 믹싱(Camelot Wheel)** 과
**에너지 아크**로 곡을 배열해, YouTube로 순차 자동재생하는 웹 앱입니다. 660곡 규모의 오디오 피처
(BPM·조성·에너지·음색)를 재활용합니다.

- 🌐 **프론트(GitHub Pages)**: https://sbb2002.github.io/bandori-playlist-maker/
- ⚙️ **백엔드(Render)**: https://bandori-playlist-maker.onrender.com
- 📄 자세한 배경/지표는 [`docs/PRD.md`](docs/PRD.md), 배포는 [`docs/DEPLOY.md`](docs/DEPLOY.md), 향후 계획은 [`docs/BACKLOG.md`](docs/BACKLOG.md).

---

## ✨ 주요 기능

| 기능 | 설명 |
|---|---|
| 자연어 요청 | "퇴근하고 기분 좋아지는 1시간 플리" 같은 한 문장 입력 |
| 무드 해석(LLM) | OpenRouter로 밝기·시작/종료 에너지·단계 수·**비단조 에너지 아크** 추출 |
| 2단계 선곡 | Stage A(에너지 허용창 하드선택 + 밝기 버킷) → Stage B(곡 경계 텐션 연속성 + 하모닉 소프트 + 오프너) |
| 하모닉 믹싱 | 이전 곡과 Camelot 인접 조성을 선호해 매끄러운 전환 |
| YouTube 순차재생 | iframe 자동재생, 이전/다음, 재생불가 곡 자동 스킵 |
| 플레이리스트 편집 | 드래그로 **순서 이동** · **곡 제거** · 트랙 사이 **곡 추가**(밴드/곡 미니 브라우저) · **Ctrl+Z 되돌리기** |
| 에너지 그래프 | 요청 해석 아크를 시각화, 드래그로 직접 지정 가능(편집 시 자동 갱신) |
| 공유 | YouTube 익명 재생목록(watch_videos)으로 열기 |
| 필터 | 밴드(프롬프트 자동감지 포함) · Original/Cover · 재생시간 · 단계 수 |
| 계측 | umami 커스텀 이벤트(생성·전환·절반청취·공유·추가) |

## 🧠 동작 방식

```
자연어 요청
   │  (POST /api/setlist)
   ▼
MoodInterpreter(포트) ──▶ OpenRouter 어댑터  또는  Stub 어댑터(오프라인)
   │        밝기 / 시작·종료 에너지 / 단계 수 / stage_energies(아크)
   ▼
선곡 엔진(순수 함수, 도메인)
   ├─ Stage A: 단계별 에너지 허용창으로 후보 하드선택(+밝기 버킷·rng 변주)
   └─ Stage B: 이전 곡 아웃트로 ↔ 다음 곡 인트로 텐션 연속성(다목적) + 하모닉 인접 소프트
   ▼
Setlist(곡 순서 + 이유 메타 + 추정 총재생시간)
   │
   ▼
프론트: 트랙리스트 렌더 → YouTube 순차재생 · 편집 · 공유
```

## 🏗️ 아키텍처 (클린/헥사고날)

도메인 로직은 외부 서비스에 직접 의존하지 않습니다. LLM 호출은 **포트/인터페이스**를 통하며
벤더 교체(OpenRouter 모델 변경, 다른 LLM 등)는 **어댑터 한 곳** 수정으로 끝납니다.

```
src/backend/app/
├─ domain/      # 모델 + 선곡 규칙(순수 함수, LLM·HTTP 무의존) — 단위 테스트 가능
├─ ports/       # MoodInterpreter 인터페이스(포트)
├─ adapters/    # openrouter_adapter · stub_adapter · prompt
├─ api/         # FastAPI 라우트 · 스키마 · 밴드 별명 자동감지
├─ repo/        # songs_master.csv 로더
└─ main.py      # composition root(어댑터 주입 · CORS · 예외 핸들러)
```

- **선곡 로직은 구조화된 LLM 출력(MoodParameters)에 대한 순수 함수** → LLM 호출 없이 테스트됩니다.
- 데이터는 `data/songs_master.csv`(660곡, 13밴드) 하나로 자기완결.

## 🧰 기술 스택

- **백엔드**: Python · FastAPI · uvicorn · pydantic · httpx (LLM: OpenRouter, 기본 `nemotron:free`)
- **프론트**: 바닐라 HTML/CSS/JS · YouTube IFrame API · umami
- **호스팅**: GitHub Pages(프론트) · Render(백엔드, 무료 플랜)

## 📂 프로젝트 구조

```
├─ src/
│  ├─ backend/        # FastAPI 앱(app/) + requirements.txt
│  ├─ frontend/       # index.html · app.js · style.css · assets/bands(밴드 아이콘)
│  ├─ scripts/        # 데이터 추출/가공(로컬 오디오 필요)
│  └─ tests/          # pytest(70+)
├─ data/              # songs_master.csv 등(읽기 전용 산출물)
├─ docs/              # PRD · architecture · DEPLOY · BACKLOG · research
├─ render.yaml        # Render Blueprint
└─ .github/workflows/ # GitHub Pages 배포
```

## 🚀 로컬 실행

```bash
# 1) 백엔드 (.env 자동 로드; OPENROUTER_API_KEY 없으면 stub 오프라인 모드)
python -m uvicorn app.main:app --app-dir src/backend --port 8000

# 2) 프론트 (정적)
python -m http.server 5500 --directory src/frontend
#    → http://localhost:5500  (localhost면 자동으로 로컬 백엔드에 연결)
```

`.env`(리포 루트 또는 `src/backend/.env`, 커밋 금지):

```
OPENROUTER_API_KEY=sk-or-...        # 없으면 stub 휴리스틱으로 동작
OPENROUTER_MODEL=nvidia/nemotron-3-nano-30b-a3b:free
FRONTEND_ORIGIN=https://sbb2002.github.io   # 배포 시 CORS 허용 오리진
```

## 🧪 테스트

```bash
python -m pytest src/tests -q      # 도메인/선곡/하모닉/에너지/API 회귀
```

## 🚢 배포

프론트(GitHub Pages) + 백엔드(Render Blueprint) 구성. 절차·환경변수·커스텀 도메인은
[`docs/DEPLOY.md`](docs/DEPLOY.md) 참조.

## 🗺️ 로드맵

포스트-파일럿 백로그는 [`docs/BACKLOG.md`](docs/BACKLOG.md): YouTube 계정 저장형 재생목록(OAuth),
공유 결과 팝업(URL 복사), 플레이리스트 프리셋(localStorage) 등.

## 📊 데이터 출처

오디오 피처·밴드 아이콘은 자매 프로젝트 [`bandori-song-sorter`](../bandori-song-sorter)에서 추출한
데이터셋을 재활용합니다(조성·BPM·에너지·음색). 곡/오디오 저작권은 각 권리자에 있으며, 오디오 원본은
커밋하지 않습니다.

## 📝 Version Log

각 커밋에서 한 일(최신순, 커밋 코드 = 우하단 표기 버전).

- `c65892d` — Groq RPM 큐제어(토큰버킷) + 동시 처리 200 입장제어(초과 시 안내·개발자 알림) + 파라미터 적극 산출 프롬프트 + 밴드필터 아이콘.
- `9734b38` — 프리셋 저장(B3): 좌측 메뉴에서 저장된 플레이리스트 열람·복원·삭제(자동저장·최대 50·Ctrl+Z).
- `6107b54` — 요약 카드를 감성 플레이버 텍스트+해시태그로 개선 + 팬메이드 푸터·우하단 버전 표기·모바일 UI.
- `07a04dd` — Groq 미활성 버그 수정(GROQ_API_KEY 키 이름 오타로 stub 폴백되던 것).
- `953b9a9` — LLM 제공자 OpenRouter → Groq 마이그레이션(하루 50회 제한 회피).
- `c78275f` — 공유 결과 팝업(B2): 생성 안내 + 공유 URL 복사 + 유튜브 듣기.
- `3ff3df8` — 루트 README(프로젝트 소개) 작성.
- `99637bd` — umami 방문자 통계 활성화(head 주입).
- `41c02f5` — 포스트-파일럿 백로그 문서(OAuth 재생목록·공유 팝업·프리셋).
- `cac8561` — 베타 배포 구성(Render Blueprint + GitHub Pages 워크플로 + 배포 가이드).
- `c211cd1` — 곡 추가 팝업에 밴드 아이콘·순서(song-sorter 동일) + 팝업 스크롤 체이닝 차단.
- `e4da922` — 곡 추가 '+'를 트랙 사이 삽입점으로 이동 + 편집 버튼 테마 조화.
- `dcf8ecf` — 플레이리스트 편집 Phase 2: 곡 추가(+) + 미니 밴드/곡 브라우저(/api/songs).
- `8488d25` — 순서이동을 '떠 있는 드래그'로 재작성 + 버튼 UI 이미지화 + 텍스트 선택 방지.
- `fb6564e` — 플레이리스트 편집 Phase 1: 순서 이동·곡 제거·되돌리기.
- `0e13f72` — 요청 간 밴드 필터 누적 버그 수정(자동감지분 일회성화).
- `08b7373` — 핸드오프에 '특정 공연 셋리스트 재현 모드' 미래 기능 추가.
- `7fa7e9f` — 토큰 초기화 대비 세션 핸드오프 명세서.
- `a9c45de` — YouTube 재생목록 공유 + 프롬프트 밴드 체크박스 동기화 버그 수정.
- `f5a804d` — 비단조 에너지 아크(활동별 LLM 단계 에너지).
- `fee6b0f` — 핵심 품질 게이트 회귀 테스트 고정.
- `a3ad276` — Stage B 시퀀싱 개선(오프너 인트로 + 경계·하모닉 다목적).
- `7b68366` — 누락 밴드 포함(various_artists·1곡 밴드 eligible 전환).
- `f35b049` — Original/Cover 곡 종류 필터.
- `8cfe36a` — 프롬프트 밴드명(별명) → 자동 밴드 필터.
- `5a0518c` — 곡 경계 텐션 연속성 시퀀싱.
- `84e8182` — 참고 PDF gitignore.
- `1f8340a` — 시간분절 강도로 '항상 시끄러운' 곡까지 포착.
- `934a5ca` — 전곡 에너지 재추출로 발췌 편향 근본 해결(energy_full).
- `9d4f44e` — 에너지 그래프가 요청 해석을 반영.
- `b8fccfa` — R&D 플레이리스트 시퀀싱 전략 연구보고서.
- `fbe91c9` — 2단계 SELECT→SEQUENCE 선곡 엔진 + 백분위 강도.
- `a16f0b7` — 무드 정확도·연속성 개선(에너지 블렌드 + 급변 방지).
- `fa16307` — 선곡 확률 상한 + 텐션 그래프 UX 개선.
- `aa6ba03` — YouTube 재생 수정 + 에너지 축 교정 + 확률적 선곡 + 텐션 그래프 UI.
- `9acae71` — 설정 기능 프로토타입(밴드 필터 + 에너지 단계 직접 지정).
- `e5bd7f9` — OpenRouter 실경로 활성화(.env 로더 + 무료 nemotron 기본).
- `67a968f` — 파일럿 프로토타입 구현(백엔드 클린아키텍처 + 정적 프론트 + 테스트).
- `a8b13bc` — 모든 코드를 src/ 하위로 이전 + 폴더별 README 규칙.
- `fc13e2e` — 아키텍처 설계서(스키마 동결).
- `83cdf9a` — songs_master.csv 생성(데이터팀).
- `920d8f1` — video_id 헬퍼 + Camelot 매핑 + 토큰 게이트 툴.
- `c53877a` — 데이터팀 보고서 + .gitignore.
- `da4ebdc` — PRD·에이전트 조직도·CLAUDE.md 초기 커밋.
