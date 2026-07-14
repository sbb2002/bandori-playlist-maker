# 🎧 Bandori-Playlist-Maker

> 한 문장이면 됩니다. 기분·상황을 말하면 **뱅드림(BanG Dream!) 곡으로 긴 재생 흐름**을 만들어 드려요.

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
├─ docs/              # PRD · architecture · DEPLOY · BACKLOG · orgarnization · next-steps
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

`v1.0.0`부터 버전 이력은 [`versionlog.md`](versionlog.md)에서 관리합니다(베타 기간 커밋별
변경 이력도 그 문서의 "Beta" 절로 이관되어 있습니다).
