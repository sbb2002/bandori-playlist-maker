# NEXT STEPS / 인수인계 (2026-07-12 기준)

다른 로컬·다른 세션에서 이어가기 위한 자체 완결형 요약. 상세 요구사항 원본은
`docs/ref/user-opinion/`의 사용자 의견 문서 참조.

## 운영 워크플로 (베타 라이브)
`main` 직접 머지 금지. **작업당 새 브랜치 → 커밋·푸시 → main 대상 PR 생성 후 정지.** 머지는 소유자가
PR 검수 후 직접. (CLAUDE.md에도 명시.)

## 진행 중 PR (소유자 검수/머지 대기)
- **PR #2** — 세부설정 우선순위 핫픽스. 브랜치 `hotfix/settings-prompt-continuity`(main 기준).
- **PR #1** — 요약 카드 해시태그 최소 2개 보장. 브랜치 `fix/summary-card-hashtags`.
- (이 문서를 담은 docs PR도 별도로 열릴 수 있음.)

### PR #2 핵심 동작 원칙 (코드 + `docs/architecture.md` 스키마3에 반영됨)
설정을 두 부류로 나눠 다룬다:
- **스코프 필터**(밴드, 커버/오리지널) = 프롬프트 의도와 무관하게 **항상 적용**(사용자가 명시적으로 좁힌 범위).
- **재생 형태 설정**(에너지 아크·단계 수·재생시간) = 직전 요청과 의도가 같을 때만 존중(LLM `same_as_previous`
  판정, 요청에 `previous_prompt` 동봉). 1회차·의도 변경 시 모델이 새로 제어. 응답 `honored_overrides`(bool)로
  노출 → 프론트가 자동 해석 시 그래프·재생시간을 새 해석으로 되돌린다.
- 그래프 UI: '에너지 단계 수' 텍스트박스 제거 → 그래프 우클릭/모바일 롱프레스로 구간 추가·제거(최소 2·최대 11).
- 진단: `/api/health`가 `interpreter`(stub|groq) 노출, `/api/setlist`에 `Cache-Control: no-store`.

### PR #2 남은 수동 검증 (헤드리스 불가 — 브라우저에서 Ctrl+F5 후 확인)
- 에너지 그래프 임의 좌표 우클릭/롱프레스 → `[여기에 에너지 단계 추가]`/`[이 에너지 단계를 제거]` 둘 다 표시.
- 추가 시 새 구간 = 앞뒤 평균, 제거 시 클릭 최근접 포인트 기준, 한계(2/11) 시 안내 메시지.
- 세부설정 안내문구가 박스 없이 하단 팬메이드 면책문구와 동일 톤.
- 그래프 조작 후 프롬프트 의도 변경 시 그래프가 새 해석으로 리셋되는지.

## 미완 작업 (핫픽스 이후, 우선순위 순)
출처: `docs/ref/user-opinion/2026-07-12-pr_rules.md`.

### 1. PR 자동머지 GitHub Actions
- **매일 AM 04:00**에 열린 PR을 자동 머지(머지·버전 패치로 인한 사용자 다운타임을 새벽에 최소화).
- 소유자가 Actions 실행 전 PR을 반려(close)하면 큐가 비므로 그냥 종료.
- 04:00에 PR 2개 이상이면 **시간 순** 수행. 패치성 PR은 작업 시점 최신 브랜치 기준으로 만들어 충돌 제거,
  데이터 추가성 PR은 데이터만 추가라 코드 충돌 없음. 패치성 PR 2개 이상이면 시간 순 처리가 중요.

### 2. 신곡 오토로더 파이프라인
- 형제 프로젝트 `bandori-song-sorter`의 Actions 기반 auto-loader와 같은 원리로, 신곡 추가 시 **미리 만든
  스크립트로 다운로드·분석 후 데이터 PR까지 자동 생성**. 그 데이터 PR은 위 04:00 자동머지에 함께 태움.
- **중요 제약**: 형제 프로젝트의 분석법은 이 앱이 쓰는 변수와 달라, 분석 방법을 현 프로젝트 곡 스키마
  (`idx, band, song, video_id, camelot, energy, mode_score, shape, eligible_band` +
  `intro_energy`/`outro_energy`, architecture.md §③ 스키마2)에 맞게 **수정** 필요. 원천 피처는
  `bandori-song-sorter`의 `song_features_with_proxies.csv`에서 파생(CLAUDE.md 데이터 소스 표 참조).

## 운영 참고 — 스텁 폴백 진단
요약 카드가 **"은은한 한결같은 흐름의 세트리스트"**(정형 문구)로 고착되면, 백엔드가 **오프라인 스텁**으로 도는
것(`GROQ_API_KEY` 미설정/미활성). 실제 LLM은 자유 서술 요약을 낸다. 확인: `GET /api/health`의 `interpreter`가
`stub`인지. 조치: 로컬은 `src/backend/.env`, 배포는 Render 환경변수에 `GROQ_API_KEY` 설정 후 재구동/재배포.
