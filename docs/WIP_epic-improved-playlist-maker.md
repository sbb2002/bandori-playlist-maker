# WIP: epic/improved-playlist-maker 작업 순서 (임시 문서)

**목적**: `research` 브랜치 `topic/20260731_audio_feats_revised/report_final.md`에서 채택한
9개 오디오 피쳐 파라미터를 실제 앱(`bandori-playlist-maker`)에 도입하는 구현 트랙. 다른
로컬/세션에서도 이어 작업할 수 있도록 순서를 기록해둔다. 완료 후에는 이 문서를 삭제하거나
`docs/architecture.md`/`docs/BACKLOG.md`로 흡수한다.

**배경 참고 문서**: `bpm-research` 워크트리(`research` 브랜치)의
`topic/20260731_audio_feats_revised/report_final.md` — 최종 채택 파라미터 9개, VIF 검증,
UI 적용 방향(백분위 슬라이더 7개 + ON/OFF 토글 1개 + 필터/태그 1개), arousal-valence 2D 맵
제안 등.

## 작업 순서

1. **아티팩트로 (energy, valence) 2D 세부설정 UI 프로토타입 제작**
   - report_final.md의 "arousal-valence 2D 맵(circumplex)" 제안을 아티팩트로 먼저
     시각화/프로토타이핑 — 실제 코드 반영 전에 UX를 검증.
2. **1)을 실제 앱에 적용 + 다른 파라미터 도입**
   - 2D 맵 UI를 `src/frontend`의 세부설정 화면에 실제로 반영.
   - 나머지 채택 파라미터(lufs_integrated, lra, danceability_norm, instr_stem_ratio,
     speech_median, acoustic_median 토글, mode 필터)도 순차 도입.
   - **정서 지도 배경 테마(2026-08-02 결정, 3안 모두 킵)**: 프로토타입에 배경 3안(1=현재
     accent 코너 라디얼, 2=사분면 4색, 3=EMOI-MAP풍 딥스페이스+별/성운)을 토글로 구현해
     비교함 — 3안 모두 유지하기로 함. 앱 반영 시 **기본값은 1안**, 추후 "설정"에서 사용자가
     2·3안 중 테마를 고를 수 있게 함(지금 단계에서 설정 UI까지 만들지는 않음). 3안(EMOI-MAP풍)은
     실제 앱에서 캔버스 BPM 펄스 애니메이션은 쓰지 않지만, 정적 데이터 포인트(별) 자체는
     구현할 예정 — 프로토타입의 CSS 정적 별은 최종본이 아니라 자리표시자.
   - **선곡 엔진 보간 로직(2026-08-02 설계 확정, 미구현)**: 구간(스테이지)의 값은 고정값이
     아니라 구간 경계점 사이를 점진적으로 보간(interpolate)한 궤적으로 다룬다. 예:
     1구간 포인트(energy=28, valence=32, loudness=30, lra=62, ...) → 2구간 포인트
     (energy=40, valence=55, loudness=48, lra=55, ...)로 급변하지 않고 점진적으로 변화.
     1구간에 곡이 3곡 배정됐다면 3곡 모두 "1구간의 고정값"으로 선곡하는 게 아니라, 1구간
     내에서 점진적으로 변화하는 세부 목표값에 따라 각 곡을 선곡한다.
     **주의**: 아직 효용성(실제 청취감 개선 여부) 검증 전이므로 이 보간 방식을 **메인
     옵션**으로, 기존 구간별 고정값 방식은 **보조 옵션**(A/B 비교·폴백용)으로 함께 구현할 것.
     선곡 엔진(도메인 순수 함수, PRD §8 하모닉 믹싱 규칙과 같은 위치)에 반영되는 로직이라
     2)의 앱 반영 범위에 포함되지만, 프론트 UI(1단계 프로토타입)와는 별개로 별도 구현 필요.
3. **외부 LLM 어댑터의 파라미터 제어 로직 수정**
   - 현재(`src/backend/app/adapters/groq_adapter.py` 등)는 단일 응답으로 파라미터를 한 번에
     채우는 방식까지만 구현됨.
   - 사용자 청취감과 괴리가 확인되면(추후 판단), 파라미터를 여러 단계로 나눠 제어하는 방식으로
     확장 — **multistage가 그 스켈레톤**(기존 에너지 단계 로직 재사용 가능한 뼈대로 참고).
   - 지금 단계에서 바로 분할 제어를 구현하지는 않음 — 필요성이 확인된 이후 착수.
4. **main vs epic 청취감 비교 → epic 우수 판정 시 머지**
   - `epic/improved-playlist-maker`(epic versioning)에서 완성된 버전과 현재 `main`을
     실제 청취 비교.
   - epic 쪽이 우수하다고 판단되면 그때 `main`으로 머지 시도(리뷰·PR 절차는 CLAUDE.md
     working agreement 따름 — owner 머지, 임의 머지 금지).

## 상태

- [x] 1) 2D UI 아티팩트 프로토타입 — `src/artifacts/valence-energy-map-prototype.html`
      (앱 `style.css` 토큰 그대로 재사용, 드래그 가능한 (valence, energy) 궤적 + 타임라인 +
      요약 문장 미리보기. 백엔드 연동 없는 UX 검증용 목업.)
- [ ] 2) 앱 반영 + 다른 파라미터 도입
- [ ] 3) LLM 어댑터 파라미터 제어 로직 수정
- [ ] 4) 청취감 비교 및 머지 판단

(2026-08-02 작성, 1) 완료 — 2)부터 이어서 진행)
