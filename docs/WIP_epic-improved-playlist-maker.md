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

- [ ] 1) 2D UI 아티팩트 프로토타입
- [ ] 2) 앱 반영 + 파라미터 도입
- [ ] 3) LLM 어댑터 파라미터 제어 로직 수정
- [ ] 4) 청취감 비교 및 머지 판단

(2026-08-02 작성, 착수 전 단계)
