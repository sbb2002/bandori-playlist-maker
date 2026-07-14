# RESUME — 신곡 오토로더 (2026-07-15 마감 시점 스냅샷)

> **이 파일은 세션 재개용 임시 메모다. PR 오픈 직전에 삭제할 것(main에 남기지 않는다).**

## 오늘까지 완료된 것

- `src/scripts/autoloader/` 구현 완료 + 단위테스트 30개 전부 통과
  (`python -m pytest scripts/autoloader -q`, src/에서). 전체 스위트 222 passed도 확인.
- **동결 norm 3계열 실데이터 재현 검증 완료** (전부 원본과 일치):
  - proxy z: 기존 660행 최대오차 **0.00e+00**
  - energy_full: **exact 658/658** — 분포 기반은 중복 업로드 제거 *전* 원시 660행
    (eligible 풀 653). master(658) 기준으로 만들면 재현 안 됨(실측 max diff 1.7e-2).
  - i_*: **exact 3960/3960, max diff 0** — 기반은 `temporal_intensity.csv`의 660곡.
    master 658곡 기준은 재현 실패(max diff 6.4e-3). 상수는 부트스트랩(약 4분, workers=6).
- E2E dry run: 신곡 3곡(idx 660 素寄曲 / 661 羅永線 / 662 騒混出) 감별→다운로드→분석
  **전 곡 성공**("반영 3곡 · 실패 0곡"). 산출 예: 660 key=Dmaj energy_full=0.031,
  661 A#maj 0.049, 662 G#maj 0.152.
- wav 3개는 형제 데브 캐시에 확보됨(재실행 시 다운로드 생략):
  `bandori-song-sorter/src/content/cluster/audio_full/mygo__66{0,1,2}.wav`

## 발견된 버그 1건 (dry 출력 단계에서 KeyError — 내일 첫 수정 대상)

`merge_data.assemble_master_row`가 `audio_entry["energy"]`/`["shape"]`를 요구하지만,
**형제 audio_map.json의 신곡 엔트리에는 이 키가 없다**(실측, pipeline 클론 songs[660]):

- 신곡 엔트리 키: `band, song, url, x, y, bpm`  (energy 없음, shape 없음)
- 구엔트리 키:   `band, song, url, x, y, bpm, energy`  (shape는 구엔트리에도 없음!)
- 즉 master의 `shape`는 예전 스냅샷(우리 `data/audio_map.json` 사본)에만 있고,
  형제 최신 audio_map에는 더 이상 없다. `energy`도 신곡부터는 안 만들어진다.

수정 방향(내일 결정·구현):
- master `energy`(EMOI 펄스 발췌 에너지) / `bpm`: 앱(song_repo)이 **소비하지 않는** 레거시
  컬럼 → 신곡은 `energy=""` 허용이 간단. bpm은 엔트리에 있으니 그대로.
- master `shape`: song_repo가 **소비함**(Song.shape). 형제 소스가 사라졌으니
  ① 형제의 shape 산출 로직(build_audio_map.py / append_song_map.py에서 확인)을 이식해
  직접 계산하거나 ② mode_score 기반 근사(bright/neutral/dark 경계값을 기존 데이터에서 역산)
  중 택1. **먼저 형제 레포에서 shape가 어떻게 계산됐는지 확인할 것.**
- `_post_checks`의 신규 행 파싱 검증도 energy 공란 허용으로 맞출 것.
- 수정 후 `test_merge_data.py`에 "신곡 엔트리에 energy/shape 없음" 케이스 추가.

## 내일 재개 순서

1. 위 버그 수정(+테스트) → `python -m pytest scripts/autoloader -q`
2. dry run 재실행(다운로드는 캐시라 수 초):
   `python src/scripts/autoloader/run_autoloader.py --repo-root C:\Users\User\Documents\pyworks\bpm-data-branch --dry`
3. 산출 행 검수 후 실반영(같은 명령에서 --dry 제거) → 데이터 검증
   (master 661행, song_repo.load_songs() 스모크, src/ pytest)
4. **이 파일 삭제** → versionlog v1.7.0의 PR 번호 확인·확정 → `v1.7.0` 태그 →
   push → 툴 PR(base main) 오픈하고 정지
5. data 워크트리(`bpm-data-branch`, 브랜치 `data`)에서 데이터 9파일 커밋
   (`data: 신곡 자동 반영 3곡 — …`) → push → **PR만 오픈, 머지는 소유자**
   (사용자 확정: data 브랜치 자동 main 머지는 PR 자동머지 Actions 도입 후)

## 환경/워크트리 메모

- 이 브랜치: `feature/song-autoloader` (워크트리 `C:\Users\User\Documents\pyworks\bpm-feature-song-autoloader`)
- data 브랜치 워크트리: `C:\Users\User\Documents\pyworks\bpm-data-branch` — **untracked로
  동결 norm 3종이 이미 생성돼 있음**(`data/feature_norms.json`·`energy_full_norm.json`·
  `intensity_norm.json` — intensity 재부트스트랩 불필요, 커밋만 하면 됨)
- 데브 레포 워킹트리(research/mood-warmth-feature)는 건드리지 않았음
- versionlog.md의 v1.7.0 항목은 이 WIP 커밋에 포함(기준 커밋 d369745, PR #32 예측 —
  PR 생성 후 번호 어긋나면 정정 커밋)
