# wav → video_id → 최신 idx 복구 검증 리포트

- 조사일: 2026-08-01
- 대상: `bandori-song-sorter/src/content/cluster/audio_full/*.wav` 743개
- 목적: `{band}__{idx:03d}.wav` 파일명의 idx가 여러 차례의 `build_manifest.py` 전역
  재빌드로 어긋난 상태에서, 각 wav가 실제로 어느 곡(video_id)인지 복구하고 최신
  `songs_full.csv` 기준 올바른 idx를 찾는다.
- **읽기 전용 조사**. `bandori-song-sorter`에는 어떤 파일도 쓰기/커밋하지 않았음
  (untracked 파일 `fetch_log.txt`, `manifest_backfill_41songs.csv`,
  `manifest_backfill_new_onsets.csv`, `manifest_pipeline.csv`, `run_pipeline.ps1`도
  읽기만 하고 그대로 둠).

## 방법론

1. `audio_full/*.wav` 743개의 파일시스템 mtime(never renamed → 다운로드 시각 그대로
   보존)을 초 단위로 수집.
2. `git log --follow -- src/content/cluster/songs_full.csv` 로 이 파일을 건드린
   전체 커밋 히스토리(10개 — 9개 과거 커밋 + 현재 HEAD)를 시각순으로 확인.
3. 각 커밋 시점의 `songs_full.csv` 스냅샷을 `git show <hash>:<path>` 로 조회(체크아웃
   없이) 하여 스크래치패드에 저장.
4. 각 wav의 mtime보다 **직전(또는 거의 동시, 1분 유예)** 인 가장 최신 스냅샷을
   선택 → 그 스냅샷에서 `(band, cached_idx)` 정확히 일치하는 행을 찾아 `url` →
   `video_id` 파싱(`build_manifest.py`의 `video_id()` 로직 그대로 재사용).
5. 복구된 video_id를 **현재 HEAD**(commit `8797d7a6`, 2026-07-26 17:33, 730곡)의
   `songs_full.csv`에서 video_id로 역탐색 → `matched_band/matched_song/correct_idx`
   확정.
6. 매칭 실패 시 인접 스냅샷으로 폴백 시도 후에도 실패하면 `unresolved`로 표시.

### mtime ↔ 커밋 대응 (재확인 결과)

| 커밋 | 커밋 시각 | 스냅샷 곡수(누적) | 해당 wav 배치 |
|---|---|---|---|
| `ab230708` | 07-03 10:52 | 660 | 07-03/07-04 초기 전곡 수집 660개 |
| `a146ede4` | 07-15 00:28 | 663 | mygo 3곡(660-662) |
| `c0c997c1` | 07-19 01:40 | 664 | millsage 1곡(663) |
| `e3798341` | 07-20 12:04 | 665 | (ikka_dumb_rock 1곡 추가되었으나 **wav 없음** — idx 179, 최신 기준 미다운로드) |
| `0859af50` | 07-25 03:16 | 673 | mugendai_mutype 8곡(665-672) |
| `ee6687da` | 07-25 04:56 | 689 | mygo 커버 16곡(673-688) |
| `0718ea6d` | 07-25 09:53 | 689 | (커버 접미사 수정만, 곡수 변화 없음 → wav 배치 없음) |
| `2200c27d` | 07-26 13:10 | 689 | (커버 접미사 수정만 → wav 배치 없음) |
| `d2d431fc` | 07-26 15:49 | 730 | 41곡 백필(morfonica·mugendai_mutype·poppin_party·roselia·raise_a_suilen) → 07-26 16:00-16:24 사이 53개 wav |
| HEAD(`8797d7a6`) | 07-26 17:33 | 730 (songs_full.csv 변경 없음, onset/energy만 추가) | — |

07-31 mugendai_mutype 2곡(idx 730, 731)은 **어느 스냅샷에도 대응하는 곡이 없음**
(현재 HEAD도 730곡, idx 0-729까지만 존재) — 아래 "미해결" 참고.

## 결과 통계

- 전체 wav: **743개**
- 복구 성공(**match_confidence = high**): **741개** (99.7%)
  - 전량 `matched_band == cached_band` (파일명에 band가 이미 포함되어 있어
    밴드 자체가 바뀔 여지는 없음 — 재넘버링은 idx만 바뀜)
  - 폴백(인접 스냅샷) 필요 건수: **0건** — 모든 wav가 자신의 직전 스냅샷에서
    `(band, cached_idx)` 완전 일치로 1차 매칭됨. mtime↔커밋 대응의 신뢰도가 높다는
    방증.
- **unresolved: 2개** (`mugendai_mutype__730.wav`, `mugendai_mutype__731.wav`)
- 매칭된 741개가 가리키는 **고유 correct_idx: 729개** / 730개 중
  - 커버되지 않는 idx 1개: **idx 179 = ikka_dumb_rock · "Keep on Riddim"**
    (07-20 커밋으로 매니페스트엔 추가됐지만 실제 오디오는 한 번도 다운로드된 적
    없음 — `e3798341` 커밋 직후 fetch가 누락된 것으로 보임)
  - 중복 다운로드(같은 video_id, 다른 cached_idx의 wav 2개): **12쌍**
    (모두 mugendai_mutype, raise_a_suilen — 아래 표)

### 중복 다운로드 12쌍 (동일 곡, 신/구 idx 파일명 둘 다 존재)

| correct_idx | wav 파일 2개 |
|---|---|
| 260 | mugendai_mutype__257.wav / mugendai_mutype__260.wav |
| 261 | mugendai_mutype__258.wav / mugendai_mutype__261.wav |
| 262 | mugendai_mutype__259.wav / mugendai_mutype__262.wav |
| 266 | mugendai_mutype__665.wav / mugendai_mutype__266.wav |
| 267 | mugendai_mutype__666.wav / mugendai_mutype__267.wav |
| 268 | mugendai_mutype__667.wav / mugendai_mutype__268.wav |
| 269 | mugendai_mutype__668.wav / mugendai_mutype__269.wav |
| 270 | mugendai_mutype__669.wav / mugendai_mutype__270.wav |
| 271 | mugendai_mutype__670.wav / mugendai_mutype__271.wav |
| 272 | mugendai_mutype__671.wav / mugendai_mutype__272.wav |
| 273 | mugendai_mutype__672.wav / mugendai_mutype__273.wav |
| 594 | raise_a_suilen__525.wav / raise_a_suilen__594.wav |

각 쌍은 `recovered_video_id`가 완전히 동일함을 개별 확인함(우연 충돌 아님).
9개 method 재추출 시 이 12곡은 둘 중 하나만 쓰면 되고, 어느 쪽을 쓰든 결과는
동일해야 한다(동일 오디오의 재다운로드본).

## 52개 충돌 idx(파일명 숫자 기준)의 실제 해소

과제에서 언급된 "743개 중 고유 idx 691개(52개 idx가 서로 다른 곡에서 중복
사용)"는, **파일명의 밴드 접두사 덕분에 완전히 해소된다.** 즉 같은 정수 idx를
공유하는 두 wav는 항상 서로 다른 밴드이고, 각 밴드는 각자의 다운로드 시점
스냅샷에서 정확히 하나의 곡에 대응한다 — 실제 충돌(같은 밴드가 같은 idx를 서로
다른 두 곡에 쓴 경우)은 **0건**.

52개 idx의 분해:
- **idx 239** — 1쌍: `morfonica`(현재 idx 239 그대로) ↔ `mugendai_mutype`(현재
  idx 242로 이동)
- **idx 260-308 중 39개** — `mugendai_mutype`(idx 대부분 그대로 유지, 260대는
  약간 뒤로 밀림) ↔ `mygo`(idx 309대·365로 이동) 또는 ↔ `pastel_palettes`(idx
  369-376으로 이동)
- **idx 558** — `poppin_party`(그대로) ↔ `raise_a_suilen`(idx 627로 이동)
- **idx 594** — `raise_a_suilen`(그대로, 위 12쌍 중 하나이기도 함) ↔
  `roselia`(idx 663으로 이동)

정확한 52개 전체 목록은 `wav_video_id_mapping.csv`에서 `cached_idx` 기준으로
group-by 하면 재현 가능하다.

## 미해결 2건 — `mugendai_mutype__730.wav`, `mugendai_mutype__731.wav`

- mtime: 2026-07-31 20:06:54 / 20:07:52 — **가장 최근 커밋(HEAD, 07-26 17:33)보다
  5일 뒤**. 즉 이 두 파일은 마지막으로 알려진 `songs_full.csv` 상태 이후에
  로컬에서 실행된 무언가(파이프라인 재시도?)로 다운로드된 것으로 보이나, 그
  실행이 만들어낸 매니페스트 상태는 **커밋되지 않았고 현재 작업 트리에도 남아있지
  않다**(`git status`로 `src/content/songs/*.yaml` 변경 없음 확인, untracked
  `manifest_pipeline.csv`/`fetch_log.txt`에도 idx 730/731이나 07-31 관련 기록
  전무).
- 현재 HEAD를 로컬에서 재빌드(`build_manifest.py --out <scratch>`)해도 여전히
  730곡(idx 0-729)만 나와 이 두 파일에 대응하는 곡이 전혀 없음을 재확인함.
- **video_id를 알아낼 근거가 전혀 없어 강제로 채우지 않고 unresolved로 남김.**
  현재 mugendai_mutype 밴드는 최신 yaml 기준 69곡 전부 idx 239-308 범위에서
  이미 매칭 완료된 상태이므로, 이 2개가 이미 매칭된 69곡의 "세 번째 사본"일
  가능성보다는, **한때 존재했다가 이후 yaml에서 제거되었거나(곡 취소) 아직
  반영 전인 미지의 곡**일 가능성이 더 높아 보인다. 확정할 수 없다.

## 산출물

- `idx_recovery/wav_video_id_mapping.csv` — 743행. 컬럼:
  `wav_filename, cached_idx, recovered_video_id, matched_band, matched_song,
  correct_idx, match_confidence, note`

## 메인 세션(songs_master.csv 갱신 담당자)이 검토해야 할 리스크

1. **idx 179(ikka_dumb_rock · Keep on Riddim)는 오디오가 아예 없다.** 9개 method
   재추출 대상에서 자동 제외되거나, 별도로 재다운로드가 필요함.
2. **12개 중복 다운로드는 그대로 둬도 무방**하지만, 재추출 파이프라인이 파일명
   폴더를 그대로 스캔한다면 같은 곡이 두 번 처리될 수 있음 — video_id 기준으로
   dedup 권장.
3. **07-31의 미해결 2개(mugendai_mutype 730/731)는 방치해도 안전**하다 — 현재
   최신 songs_full.csv 730곡 중 어느 것과도 매칭되지 않으므로, 9개 method
   추출 시 이 2개 wav는 그냥 스킵하면 됨(가짜 idx로 잘못 매핑되어 다른 곡의
   데이터를 오염시킬 위험이 없다는 뜻).
4. **전체 매칭이 "폴백 0건, band 불일치 0건"으로 매우 깨끗하게 떨어졌다는 점은
   긍정적 신호이지만**, 이는 어디까지나 mtime과 커밋 이력이 우연히 잘 들어맞았기
   때문이며, 표본이 10개 스냅샷·13개 밴드로 크지 않다. 실제 `songs_master.csv`
   갱신 전에 최소 5-10곡을 무작위로 뽑아 **직접 청취 스팟체크**(wav 파일 재생 vs
   `matched_song`의 YouTube 링크 실제 곡 비교)를 한 번 거치는 것을 권장한다 —
   특히 mugendai_mutype처럼 여러 번 재넘버링을 겪은 밴드 위주로.
5. 이 검증은 `data/songs_master.csv`를 갱신하지 않았다. 갱신 작업은 이 CSV를
   근거로 별도로 진행할 것.
