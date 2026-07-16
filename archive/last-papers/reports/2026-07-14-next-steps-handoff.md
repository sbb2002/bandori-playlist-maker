# NEXT STEPS / 인수인계 (2026-07-14 기준)

> **[2026-07-16 이관]** 원래 `main`의 `docs/next-steps.md`였다. Google 심사 대기 항목을 제외한
> 나머지는 이미 오래된 스냅샷이 되어 `main`에 둘 이유가 없어져 이 브랜치로 이관했다(직전에
> PR #20 머지 완료·`research` 단일 브랜치 통합·신곡 오토로더 PR 없는 방식으로 완료 등, 이관
> 시점까지 파악된 정정만 반영). 이후 갱신은 없다 — 특정 시점 기록으로 취급.

다른 로컬·다른 세션에서 이어가기 위한 자체 완결형 요약. 상세 요구사항 원본은
`document-archive` 브랜치의 `archive/ref/user-opinion/`에 있는 사용자 의견 문서 참조.

**현재 배포 버전: `v1.6.2`** (= `main` HEAD, 2026-07-14 시점). 태그 이력은 `main`의
`versionlog.md` 참조.

## 운영 워크플로 (베타 라이브)
`main` 직접 머지 금지. **작업당 새 브랜치 → 커밋·푸시 → main 대상 PR 생성 후 정지.** 머지는 소유자가
PR 검수 후 직접. (CLAUDE.md·`git-rules.md`에도 명시.)

---

## ⏳ 결과 대기 중 — Google 심사 2건 (가장 중요)

**둘 다 우리가 할 수 있는 조치는 끝났고, Google의 회신만 기다리는 상태다. 결과가 오기 전까지
이 건으로 코드를 더 건드릴 필요 없다.** 회신이 오면 아래 "결과가 오면 할 일"을 수행한다.

### A. OAuth 앱 인증(verification) 심사 — 제출 완료, 대기 중
- **제출일**: 2026-07-13. 스코프 `youtube.force-ssl`(민감 등급) 사용에 대한 인증 심사.
- **왜 필요한가**: 미인증 상태에서는 Cloud Console에 등록된 **테스트 사용자 100명만** 로그인 가능하고,
  그 외 사용자는 OAuth 팝업에서 "Access blocked — has not completed the Google verification process"
  화면만 보게 된다. 즉 **일반 베타 사용자는 "내 재생목록에 넣기"를 쓸 수 없다.**
- 제출물: 개인정보처리방침 URL, 데모 영상(YouTube 미공개, Cloud Console에 `youtu.be/aZg5vabYF0c` 등록),
  스코프 사용 근거(영문). 승인된 도메인은 Search Console **URL 접두어 속성**
  `https://sbb2002.github.io/bandori-playlist-maker/`로 인증(도메인 속성 불가 — `github.io`는 Public
  Suffix List 도메인).
- **알려진 증상(정상)**: 미인증 상태라 동의 화면에 앱 이름 대신 도메인(`sbb2002.github.io`)이 뜨고,
  개인정보처리방침/약관 링크가 표시되지 않는다. 인증 통과 시 자동 해소된다.

### B. YouTube Data API 할당량(quota) 증설 신청 — 제출 완료, 대기 중
- **제출일**: 2026-07-14. 접수 확인 메일 수신함.
- **왜 필요한가 (A와 별개 문제)**: 기본 할당량 **10,000유닛/일은 프로젝트 전체(모든 사용자 합산)** 다.
  `playlists.insert`(50) + `playlistItems.insert`(50 × 곡수) → **60분 플리 1개 ≈ 900유닛**
  → **하루 약 11회가 전 사용자 합산 상한.** 180분(약 50곡)이면 2,550유닛이라 헤비 유저 1명이
  하루치의 1/4을 태운다.
- **인증(A)이 통과되면 오히려 이 문제가 드러난다** — 지금은 테스트 사용자만 써서 한도에 안 닿을 뿐이다.
- 제출물: 개인정보처리방침·서비스 약관 스크린샷, 홈페이지 스크린샷, OAuth 흐름(동의·범위·철회) +
  임베드 플레이어 증빙, 아키텍처/유저플로우/부속자료 설계 문서. 증빙 파일은
  `docs/audit_evidence/`(gitignore — 개인정보 포함, 로컬 보관).

### 결과가 오면 할 일
- **A 승인 시**: 코드 변경·배포 불필요. Cloud Console 설정이라 승인 즉시 일반 사용자에게 정상 동의 화면이
  뜨고 각자 계정에 저장된다. 동의 화면의 앱 이름·정책 링크 표시도 정상화된다.
  - 이때 Cloud Console **브랜딩 → 서비스 약관 링크**가 비어 있으면 채운다:
    `https://sbb2002.github.io/bandori-playlist-maker/terms.html`
- **A 반려 시**: 반려 사유를 확인해 재제출. 과거 반려 사유는 (1) 홈페이지 소유권 미확인,
  (2) 앱 이름 불일치, (3) 브랜딩(로고) 미노출 — 모두 해소된 상태다.
- **B 승인 시**: 별도 조치 없음. 할당량이 자동 상향된다.
- **B 반려/미승인 시**: 하루 ~11회 상한이 유지된다. 앱은 죽지 않고 **익명 임시 재생목록으로 폴백**
  하지만(v1.6.1), 사용자 경험상 아쉬우므로 `403 quotaExceeded`를 따로 잡아 "오늘 저장 한도를 다
  썼어요(내일 초기화)" 전용 메시지를 넣는 것을 검토한다. (현재는 일반 실패 메시지 + 폴백.)

---

## 진행 중 PR (소유자 검수/머지 대기) — 이관 시점(2026-07-16) 기준 갱신
- **PR #14** (`docs` 브랜치, 현 `document-archive`) — boundary_tension 조사 메모 + DEPLOY.md 정정 +
  v1.1.0~v1.6.2 버전 이력 + audit_evidence gitignore + 이 문서.
- **PR #20** (`research/boundary-tension-sensitivity`) — **머지 완료.** 원인 규명 결과(아래 1번)에
  대한 **후속 결정 자체는 아직 미해결**로 남아있음. (`research/boundary-tension-sensitivity`
  브랜치는 2026-07-16부터 `research` 단일 브랜치 체계로 통합돼 더 이상 존재하지 않음 — 이
  보고서는 `document-archive`의 `archive/research/`에 그대로 있음.)

---

## 미완 작업 (우선순위 순)

### 1. 선곡 엔진의 전역 민감도 (R&D 결론 나옴 → 코드 작업 여부 결정 필요) — 여전히 미해결
- **PR #20에서 원인 규명 완료.** 곡 2개 제거만으로 회귀가드 실측값이 크게 튄 원인은 RNG 정렬이 아니라
  (그 가설은 **반증**됨), `song_repo._percentile_ranker()`가 `Song.energy`를 **후보 풀 전체 분포의
  percentile**로 계산하기 때문이다. 곡이 몇 개만 빠져도 나머지 전곡의 energy가 미세 재계산되어
  Stage A 정렬 키(`abs(energy-target), idx`)의 동점 근방 순서가 뒤집히고, 같은 seed라도 선곡이 달라진다.
- **함의**: 곡 데이터가 추가/제거될 때마다(신곡 오토로더가 도입되면 상시 발생) 기존 회귀 테스트 실측값이
  흔들린다. 상세는 `document-archive` 브랜치의
  `archive/research/2026-07-14-boundary-tension-rng-sensitivity-verified.md`.
- **다음 결정**: 이를 실제 결함으로 보고 고칠지(예: energy를 절대 스케일로 고정), 아니면 특성으로 두고
  테스트 임계값만 관리할지. 고치기로 하면 **새 `feature/*` 브랜치**에서 작업한다(research 브랜치를
  그대로 main에 머지하지 않는다 — `git-rules.md`).
- **[이관 시점 추가 메모]** 신곡 오토로더(아래 3번)가 실제로 상시 반영을 시작해, 더 이상 미룰 수
  없는 상태가 됐다.

### 2. PR 자동머지 GitHub Actions — 미착수
출처: `document-archive` 브랜치의 `archive/ref/user-opinion/2026-07-12-pr_rules.md`.
- **매일 AM 04:00**에 열린 PR을 자동 머지(머지·버전 패치로 인한 사용자 다운타임을 새벽에 최소화).
- 소유자가 Actions 실행 전 PR을 반려(close)하면 큐가 비므로 그냥 종료.
- 04:00에 PR 2개 이상이면 **시간 순** 수행. 패치성 PR은 작업 시점 최신 브랜치 기준으로 만들어 충돌 제거,
  데이터 추가성 PR은 데이터만 추가라 코드 충돌 없음. 패치성 PR 2개 이상이면 시간 순 처리가 중요.
- 함께 검토: `git-rules.md`의 **자동 태깅 CI**(feature=Minor, hotfix=Patch, docs/data=Skip)가 아직
  미구축이라 현재 태그·`versionlog.md`를 수동 관리 중이다.

### 3. 신곡 오토로더 파이프라인 — ✅ 완료(단, 아래 설계로 — PR 방식 아님)
- 이 항목을 적을 때 구상한 "데이터 PR 자동 생성 + 04:00 자동머지" 방식이 아니라, **PR 없이 직접
  커밋·푸시하는 방식**으로 2026-07-15 구현 완료됐다. `tools` 브랜치의 `auto-loader/`가 형제
  프로젝트 신곡을 감별·다운로드·분석해 `data` 브랜치에 직접 push한다(`data`는 `main`에 아예
  병합되지 않는 독립 브랜치라 애초에 PR·자동머지가 필요 없어짐 — v1.7.0, `git-rules.md`의
  `data`/`tools` 절 참조). 분석 방법은 실제로 현재 곡 스키마에 맞게 수정해 구현됐다("동결 norm"
  방식, `tools` 브랜치 `auto-loader/README.md` 참조).
- **선행 확인이었던 1번(전역 민감도) 문제는 여전히 미해결** — 신곡이 상시 반영되기 시작한
  지금 더 이상 미룰 수 없는 상태가 됐다.

---

## 운영 참고

### 스텁 폴백 진단
요약 카드가 **"은은한 한결같은 흐름의 세트리스트"**(정형 문구)로 고착되면, 백엔드가 **오프라인 스텁**으로 도는
것(`GROQ_API_KEY` 미설정/미활성). 실제 LLM은 자유 서술 요약을 낸다. 확인: `GET /api/health`의 `interpreter`가
`stub`인지. 조치: 로컬은 `src/backend/.env`, 배포는 Render 환경변수에 `GROQ_API_KEY` 설정 후 재구동/재배포.

### 로컬 구동
- 백엔드: `python -m uvicorn app.main:app --app-dir src/backend --port 8000`
- 프론트: `python -m http.server 5500 --directory src/frontend`
  — **포트 5500 필수.** `main.py`의 CORS 허용 오리진(`_DEV_ORIGINS`)이 8000/5500/3000만 포함한다.
- 테스트: `src/`에서 `python -m pytest`
