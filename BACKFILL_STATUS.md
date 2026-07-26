# 백필 현황 (2026-07-26)

> 참고 문서. `data/` 실제 반영은 아직 안 됨 — 아래 "다음 단계" 참고.

## 배경

`topic/cover_song_backfill/BACKFILL_CANDIDATES.md`(main 작업트리)가 "백필 가능
165곡"으로 분류했던 근거는 유튜브 18초짜리 게임 신곡 예고 프리뷰 클립이었고
완곡이 아니었음이 이번 재검증으로 드러남. 형제 프로젝트 `bandori-song-sorter`
쪽에서 "공식/관련 채널에 재생 가능한 완곡 영상이 실제로 있는가" 기준으로
166곡 후보를 전수 재검증했다.

## 결과 요약

| 밴드 | 후보 곡수 | 반영 완료 | 없음(공식 완곡 자체 없음) | 짧음(리믹스/축약판, 보류) | 차단(존재하나 재생 불가) |
|---|---|---|---|---|---|
| RAISE A SUILEN | 10 | 0 | 9 | 0 | 1 |
| Morfonica | 11 | 1 | 9 | 1 | 0 |
| Hello, Happy World! | 21 | 0 | 20 | 1 | 0 |
| Roselia | 22 | 1 | 21 | 0 | 0 |
| Pastel*Palettes | 12 | 0 | 11 | 1 | 0 |
| Afterglow | 17 | 0 | 16 | 1 | 0 |
| Poppin'Party | 32 | 1 | 31 | 0 | 0 |
| 무겐다이 뮤타입(멤버 개인채널) | 41 | 38 | 0 | 3 | 0 |
| **합계** | **166** | **41** | **117** | **7** | **1** |

- **없음(117곡)**: 관련 공식 채널 완곡 검색 결과 없음 — 재조사 안 함(확정 규칙).
- **짧음(7곡)**: 영상은 있으나 1~2분대 리믹스/TV Size/축약 MV — 보류.
  Fleur(Morfonica) · スタ〜リング ☆じぶん☆(헬로해피) · スキ×すき×カラフリィ(Pastel) ·
  Ahoy!! 我ら宝鐘海賊団☆(Afterglow) · 8番出口 · 夢現妄想世界 -YUNO Remix- ·
  ビッグマウス -YUNO Remix-(이상 mutype)
- **차단(1곡)**: DAYBREAK FRONTLINE(RAS) — 완곡 존재하나 한국 리전 차단 확인.

## 반영 완료 41곡 (bandori-song-sorter 측)

`bandori-song-sorter` PR #10(`feat/ras-backfill`, 오너 머지 대기)에 `new_songs.csv`
등록 + `insert_backfill.py --apply` + `songs_full.csv`/`audio_map.json` 반영까지
완료. 상세 목록은 PR #10 본문·커밋(`9cc5958`, `d8836fd`) 참고.

- Morfonica: 深海少女
- Roselia: 擬態ごっこ(×사카마타 크로에 콜라보)
- Poppin'Party: 乙女はサイコパス(×P마루사마 콜라보)
- 무겐다이 뮤타입 38곡: 나카마치 아라레 12·미네츠키 리츠 6·후지 미야코 7·
  미야나가 노노카 5·센고쿠 유노 8 (개인채널 "歌ってみた" 커버)

## 다음 단계 (이 브랜치 `data/`에 아직 반영 안 됨)

1. `bandori-song-sorter` PR #10 오너 머지 대기.
2. 머지 후 `tools` 브랜치 `auto-loader/autoloader/run_autoloader.py` 실행 —
   형제 origin/main과 이 저장소 `data/songs_master.csv`의 차이(신곡 41곡)를
   감별해 오디오 다운로드+분석 후 이 브랜치에 자동 커밋·푸시(PR 없음).
3. 반영 후 `versionlog.md`에 Patch 항목(추가 41곡 목록·총 곡 수) 기록 필요.

## 재조사 금지 목록

위 "없음"(117곡)·"짧음"(7곡)·"차단"(1곡) 판정은 확정됨 — 향후 세션에서 동일
곡을 다시 검색하지 말 것. 상세 사유·개별 곡명은
[claude 메모리](https://github.com 미해당, 로컬 세션 메모리 `backfill-fullversion-verification-status.md`)
및 `bandori-song-sorter` PR #10/#9 참고.
