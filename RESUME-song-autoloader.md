# RESUME — 신곡 오토로더 (2026-07-15 마감 시점 스냅샷)

> **이 파일은 멀티로컬 세션 인수인계용 노트다.** `feature/song-autoloader`는 **main에
> 머지하지 않는 영구 tool 브랜치**로 확정됐으므로(2026-07-15) 이 파일은 브랜치에 상주한다 —
> 예전의 "PR 직전 삭제 / v1.7.0 태그" 전제는 폐기. 내구성 있는 사용법·운영 규칙은
> `src/scripts/README.md`로 이관하고, 여기는 진행 중 상태·다음 재개 순서만 유지한다.

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

## 버그 1건 — 수정 완료(다른 로컬, 2026-07-15 후속 세션)

`merge_data.assemble_master_row`가 `audio_entry["energy"]`/`["shape"]`를 요구했지만,
**형제 audio_map.json의 신곡 엔트리에는 이 키가 없어** KeyError로 dry 출력이 죽던 문제.
경로/오디오 데이터가 다른 별도 로컬(`bandori-playlist-maker`, 캐시 wav 없음)에서 코드
리뷰 + 로컬 660곡 실데이터로 다음과 같이 수정·검증했다:

- `energy`: song_repo 비소비 레거시 컬럼 → `audio_entry.get("energy", "")`로 공란 허용.
- `shape`: song_repo가 **소비함**(Song.shape). 형제 `add_pulse_shape.py`
  (`bandori-song-sorter/src/tools/cluster/add_pulse_shape.py`)의 채널 산식을 확인해
  이식(①번 방향 채택) — `acoustic=z(harmonic_ratio)`, `bright=mean(z(centroid,rolloff,
  zcr,flatness))`, `shimmer=z(flux)`, 최댓값 채택·gap<0.4면 neutral(z-score ddof=0).
  형제 audio_map에 더 이상 의존하지 않고 우리 발췌 특징(`excerpt_features.extract_from_wav`
  가 이미 6개 원시 컬럼을 전부 반환)에서 직접 계산 — `norms.py`에 4번째 동결 norm
  (`data/shape_norm.json`)으로 추가(`build_shape_norms`/`compute_shape`/
  `load_or_build_shape_norms`/`verify_shape_norms`).
- **로컬 660곡 실데이터 재현 검증**: exact 659/660. 유일한 불일치는 `roselia/Neo-Aspect`
  (idx 570·588, 동명곡) — 형제 스크립트 자체 docstring이 "song 제목만으로는 조인이
  애매하다"고 경고한 기존 한계로, 우리 포팅 문제가 아님(원본도 둘 중 하나는 틀렸을
  가능성). 99% 문턱은 통과하므로 자동 구축엔 지장 없음.
- `merge_data.assemble_master_row`/`run_autoloader.py`/`test_merge_data.py`/
  `test_norms.py` 전부 갱신, 합성 데이터 기반 단위테스트 추가(실오디오 불필요).
  `python -m pytest scripts/autoloader -q` 35 passed, 전체 `python -m pytest` 231 passed.
- **주의**: 컬럼 스키마(harmonic_ratio 등)는 `research/mood-warmth-feature` 브랜치에서
  새 변수를 연구 중이라 나중에 바뀔 수 있음 — 이번 수정엔 반영 안 함(사용자 확정
  2026-07-15).
- 동결 norm의 median/MAD 정규성 가정(1.4826) 검토·백분위-순위 소비 구조 덕에 무해함을
  실측으로 확인한 상세 내용은 `document-archive` 브랜치
  `archive/reports/2026-07-15-song-autoloader-shape-fix-and-norm-methodology.md` 참고
  (`git show document-archive:archive/reports/2026-07-15-...`).

## soft-run 기능 추가 (같은 별도 로컬, 2026-07-15 세 번째 세션)

사용자 요청: intensity_norm 부트스트랩이 불가능한 환경(이 로컬 — wav 43%만 보유)에서도
신곡 다운로드·나머지 지표 반영을 막지 말고, i_*만 밴드 평균으로 임시 대체 후 나중에
제대로 준비된 환경의 run에서 재산출(백필)되게 해달라는 요청. 구현 완료:

- `norms.py`: `band_average_intensity(master_rows, band, exclude_idx=...)` 추가 — 같은
  밴드 기존 곡 i_* 평균('%.5f', 참조 행 없으면 None).
- `merge_data.py`: `patch_intensity_rows(repo_root, {idx: {i_*...}})` 추가 —
  songs_master.csv/temporal_intensity.csv의 **해당 idx 행 i_* 6컬럼만** 되짚어 갱신.
  "기존 행 바이트 불변" 불변식에 대한 의도된 예외(대상은 이전에 provisional로 표시된
  행뿐), 실패 시 두 파일 전체 스냅샷 롤백.
- `run_autoloader.py`: `--soft` 플래그 추가.
  - 다운로드 순서를 norm 준비보다 앞으로 이동(신곡 확보를 norm 성패와 분리).
  - `_prepare_norms(..., soft=)`: intensity_norm만 실패를 흡수(med=None 반환,
    intensity_ready=False) — proxy/shape/energy_full은 wav 없이도 항상 구축 가능하므로
    soft에서도 그대로 중단(진짜 버그 가능성이 높음).
  - `_process_song`: med가 None이면 `band_average_intensity`로 대체하고
    `provisional=True` 표시(참조 행조차 없으면 fail-soft 스킵).
  - 반영 후 provisional 곡은 idx→{band,song,recorded_at}을
    `data/provisional_intensity.json`에 기록.
  - **`--soft` 없이(intensity_norm 준비 가능한 정상 run) 실행하면** 새 신곡 처리 전에
    `_backfill_provisional()`이 먼저 실행 — registry의 idx들을 실측 i_*로 재산출해
    `patch_intensity_rows`로 반영하고 registry에서 제거(wav 없으면 다음 실행에 재시도,
    fail-soft).
- 단위테스트 추가: `test_norms.py::BandAverageIntensityTest`(4개),
  `test_merge_data.py::PatchIntensityRowsTest`(3개). `python -m pytest scripts/autoloader -q`
  42 passed, 전체 `python -m pytest` 238 passed.
- **후속 수정(사용자 확정)**: `_backfill_provisional`이 wav 없으면 스킵만 하던 걸,
  master의 url로 **즉시 재다운로드 시도**하도록 변경 — soft-run을 돌린 로컬과 백필을
  돌리는(메인) 로컬이 다르면 그 신곡 wav가 메인 로컬엔 원래 없는 게 정상이기 때문
  (그 곡은 이미 master의 "기존 곡"이라 detect_new가 신곡으로 재감지하지 않음).
- **미검증**: 이 로컬은 wav 커버리지가 부족해 `--soft` 경로와 백필 경로 둘 다 **합성
  데이터 단위테스트로만** 검증했다. 원래 로컬(원본 wav 있음, 원래는 intensity_norm이
  정상 구축되므로 `--soft` 자체가 필요 없는 환경)에서는 이 기능이 실사용될 일이 없을
  가능성이 높음 — 오히려 **이 로컬처럼 wav가 부분적인 제3의 환경**(예: CI, 다른 개발자
  머신)에서 유용한 경로다. 다음 재개 시 실제 `--soft` E2E는 wav 커버리지가 의도적으로
  부족한 환경에서 별도 확인 필요.

## 다음 재개 순서 (원래 로컬 — 실오디오·캐시 wav 있는 환경)

1. 위 코드 수정을 이 브랜치에서 pull(또는 병합) → `data/shape_norm.json`이 최초
   실행 시 자동 구축됨(기존 `feature_norms.json`/`energy_full_norm.json`과 동일 패턴).
2. dry run 재실행(다운로드는 캐시라 수 초):
   `python src/scripts/autoloader/run_autoloader.py --repo-root C:\Users\User\Documents\pyworks\bpm-data-branch --dry`
   — 이번엔 KeyError 없이 신곡 3곡 shape까지 포함한 행이 출력돼야 함.
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
