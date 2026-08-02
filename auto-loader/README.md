# auto-loader/ — 신곡 오토로더 (tools 브랜치)

> **브랜치 범위**: 이 브랜치(`tools`)는 사람이 로컬에서 수동 트리거하는 운영 툴만 담는다
> (2026-07-15 `feature/song-autoloader` → `tools` 정식 승격, 2026-07-16 `src/scripts/` →
> `auto-loader/`로 재배치). `main`(배포 앱 소스)에는 **머지하지 않는다** — 앱 소스·문서 등
> 이 툴 구동에 불필요한 파일은 이 브랜치에 두지 않는다. 산출 데이터는 `data` 단일 브랜치로
> 자동 커밋·푸시한다(PR 없음, `data`도 `main`에 병합되지 않는 독립 브랜치).

## 빠른 시작

```
cd auto-loader
python autoloader/run_autoloader.py --dry                       # 검증만(파일 미변경)
python autoloader/run_autoloader.py --repo-root <data브랜치 워크트리>  # 실반영 + data 브랜치 자동 push
```
곡 감별 → 다운로드 → 지표 산출 → `data/` 반영까지 한 번에 도는 원커맨드다. 세부 흐름·플래그는
아래 "autoloader/" 절 참조.

## 전체 운영 순서 (2026-08-03 확정)

신곡 반영은 3단계로 나뉜다 — **①·②는 평소 cmd(Windows)에서, ③만 가끔 WSL2에서.**
전체를 WSL로 옮길 필요는 없다, essentia-tensorflow/torch가 필요한 ③ 하나만 WSL 전용이다.

1. **`run_local.py`**(형제 프로젝트 `bandori-song-sorter`) — 신곡 감지, cmd.
2. **`autoloader/run_autoloader.py`**(이 저장소) — 신곡 반영, cmd. `m4-lufs_integrated`·
   `m4-lra`·`m7-danceability_norm`(가벼운 3개, `pyloudnorm`/`librosa`만 필요)은 이 단계에서
   자동으로 채워진다. `m6-valence_median`·`m9-instr_stem_ratio`·`m11-speech_median`(무거운
   3개)은 이 단계에서 항상 빈 칸으로 남는다 — 의도된 동작.
3. **`data/enrich_heavy_feats.py`**(이 저장소) — 무거운 3개 보강, **WSL2 전용**, 주기적/수동
   실행. 매번 신곡마다 돌릴 필요 없이 밀린 곡이 쌓이면 가끔 실행. 자세한 실행법은 아래
   "data/" 절 참조.

WSL2가 준비 안 된 로컬에서는 ①·②만 평소대로 돌리면 되고, ③은 WSL2가 있는 로컬에서
나중에 몰아서 처리해도 무방하다(멱등 — 이미 채워진 행은 건드리지 않음).

## 작성규칙

1. **표준 라이브러리만** 사용한다 — venv 없이 바로 실행 가능해야 한다.
   - **오디오 스택 예외**: 오디오 분석 계열(`data/extract_full_energy.py`,
     `data/extract_temporal_intensity.py`, `data/build_energy_full.py`, `autoloader/`)은
     numpy/librosa/soundfile/scipy(+다운로드는 yt-dlp, ffmpeg 폴백 imageio_ffmpeg)를 쓴다.
     오디오 스택이 설치된 env에서만 실행하며, 단위 테스트는 오디오·네트워크 없이 도는
     순수 로직만 다룬다.
2. 모든 모듈은 짝이 되는 `test_*.py` 단위 테스트를 같은 폴더에 둔다. `autoloader/`·`data/`
   양쪽 다 패키지(`__init__.py`)가 아니라 `unittest discover`가 상위 `auto-loader/`에서
   한번에 재귀하지 않으므로, 폴더별로 나눠 실행한다:
   `python -m unittest discover -s auto-loader/autoloader -p "test_*.py"`
   `python -m unittest discover -s auto-loader/data -p "test_*.py"`
3. 산출 데이터는 `--repo-root`로 지정한 `data` 브랜치 워크트리의 `data/`에 쓴다(멱등 — 재실행
   시 덮어쓰기). `data/` 원본 소스는 외부 레포 `bandori-song-sorter`이며 읽기 전용이다.
4. 경로는 `Path(__file__)` 기준으로 계산한다 (cwd 무가정). repo 루트까지의 `.parent` 단수는
   파일 깊이에 따라 다르므로, 각 파일에서 직접 계산하고 단계별 주석을 남긴다
   (`data/build_master.py` 상단 예 참조).

## autoloader/ — 신곡 오토로더 (로컬 원커맨드)

형제 프로젝트(`bandori-song-sorter`)의 semiauto-loader를 이 프로젝트 데이터 스키마에 맞게
재구성한 신곡 반영 파이프라인. **감지(RSS·Telegram)는 형제 Actions가 전담**하고, 여기서는
형제 origin/main에 반영된 곡과 `data` 브랜치 `data/songs_master.csv`의 차이만 처리한다.

```
python autoloader/run_autoloader.py --dry     # 검증(파일 미변경)
python autoloader/run_autoloader.py --repo-root <data브랜치 워크트리>
                                                # data/ 반영 + data 브랜치 자동 커밋·푸시
python autoloader/run_autoloader.py --no-git   # data/ 반영만, 커밋·푸시 생략
python autoloader/run_autoloader.py --soft     # 부분 wav 환경 긴급 반영(아래)
```
(위 명령은 모두 `auto-loader/` 디렉터리 안에서 실행한다는 전제 — "빠른 시작" 참조.)

- 흐름: 감별(`sources.py`) → yt-dlp 다운로드(`fetch_new.py`, 집 IP 전제) → 45s excerpt
  특징(`excerpt_features.py`, 형제 로직 벤더링) + 전곡 서브피처/시간분절 강도(기존
  `data/extract_*` 모듈 재사용) → **동결 norm**(`norms.py`)으로 proxy·energy_full·i_*·shape
  산출 → `data/` 6파일 원자 반영(`merge_data.py`, 실패 시 전체 롤백).
- **동결 norm 원칙**: 기존 658행은 바이트 불변, 신곡만 원래 분포(원시 660곡 기준)에
  대입한다. 동결 상수 4종을 `data/feature_norms.json`·`data/energy_full_norm.json`·
  `data/intensity_norm.json`·`data/shape_norm.json`으로 영속화하며, 최초 구축 시 기존 행
  재계산 대조로 검증한다(proxy 최대오차 0, energy_full exact 658/658, shape exact 659/660,
  i_* exact 3960/3960 확인 — 2026-07-15). `shape`는 형제 audio_map 신곡 엔트리에서 필드가
  사라져(형식 변화) 형제 채널 산식(z-score ddof=0)을 이식해 우리 발췌 특징에서 직접 계산한다.
- **soft-run(`--soft`)**: `intensity_norm` 부트스트랩은 원본 **전곡** wav를 요구해, wav
  캐시가 부분적인 로컬(예: 285/660곡)에서는 신곡 반영이 통째로 막힌다. `--soft`는 이때
  중단하는 대신 신곡의 `i_*`(시간분절 강도)만 **같은 밴드 기존 곡 평균**으로 임시 대체하고
  `data/provisional_intensity.json`에 idx를 기록한다(proxy·energy_full·shape·key 등 나머지는
  실측 — `i_*`만 전곡 wav가 필요한 유일 계열이라 근사 대상이 이 6컬럼뿐). **`--soft` 없이**
  (intensity_norm 구축이 가능한 정상 환경에서) 실행하면 새 신곡 처리 전에 registry의 idx를
  실측 `i_*`로 재산출해 해당 행만 되짚어 갱신(백필)하고 registry에서 제거한다. 백필 시 그
  곡 wav가 로컬에 없으면(soft-run 로컬과 백필 로컬이 다르면 정상) master url로 재다운로드 후
  진행한다. 운영 시나리오: **타 로컬에서 `--soft`로 일단 곡 반영 → 원본 wav 있는 메인
  로컬에서 일반 run으로 정밀 산출값까지 마무리.**
- 데이터 반영은 `data` 단일 브랜치에 자동 커밋·푸시한다(기본 동작, PR 없음). `data`는
  `main`에 병합되지 않는 독립 브랜치다 — 배포된 backend가 런타임에 `data` 브랜치를 직접
  원격 fetch하므로(`main`의 `src/backend/app/repo/remote_source.py`) main 병합 자체가
  애초에 불필요하다.
- 재실행 안전: video_id 기준 감별이라 멱등, 실패 곡은 다음 실행에서 자동 재시도.

## data/ — 수동/반자동 보강 스크립트

라이브 오토로더(`autoloader/`)가 처리하기엔 의존성이 너무 무거운 작업들을 모아 둔 폴더.
대부분은 **전곡 처리가 필요 없고**, 필요할 때만 로컬에서 수동 트리거한다.

### enrich_heavy_feats.py — 무거운 3개 지표 주기적 보강

**목표**: `songs_master.csv`의 `m6-valence_median`, `m9-instr_stem_ratio`, 
`m11-speech_median` (감정 밝기, 보컬/악기 비중, 음절 밀도)을 주기적으로 실측값으로 보강.

**의존성**: essentia-tensorflow, librosa, scipy, torch (WSL2 필요)
  - 없으면 명확한 안내 후 조용히 종료(fail-soft).
  - Debian 계열 WSL2는 PEP 668(externally-managed-environment)로 시스템 파이썬에 바로
    `pip install`이 막혀 있다 — venv 필수: `python3 -m venv .venv && source .venv/bin/activate`
    후 그 안에서 설치·실행. (`python` 명령이 없다는 에러가 뜨면 `python3`를 대신 쓰거나
    `sudo apt install python-is-python3`.)

**실행**:
```bash
cd auto-loader
python data/enrich_heavy_feats.py --limit 2      # 스모크테스트: 앞 2곡만
python data/enrich_heavy_feats.py --idx 24,25    # 특정 idx만
python data/enrich_heavy_feats.py                # 전체 배치(실제 운영)
```
경로 기본값(형제 디렉토리 관례: `bpm-data-branch`/`bandori-song-sorter`/
`bandori-playlist-maker`)이 로컬 배치와 다르면 `--repo-root`/`--audio-dir`/`--stem-dir`로
덮어쓴다.

**동작**:
  1. `songs_master.csv`에서 3개 지표 중 하나라도 빈 행 탐지.
  2. 로컬 오디오 캐시(`bandori-song-sorter/src/content/cluster/audio_full/`)에서 wav 찾기.
  3. 각 곡별로 3개 파이프라인 실행:
     - `m6-valence_median`: essentia emoMusic 2단계 모델 (모델 경로는 환경변수 `ESSENTIA_EMBEDDING_MODEL`, 
       `ESSENTIA_EMOMUSIC_MODEL` 또는 생략 — 이 환경에 보통 없음).
     - `m9-instr_stem_ratio`: 보컬 스템 에너지비 (스템 없으면 자동 스킵).
     - `m11-speech_median`: Scheirer-Slaney 4Hz 변조 에너지 (스템 기반, 스템 없으면 스킵).
  4. CSV 안전한 부분-패치 (merge_data.patch_intensity_rows 패턴 모방, 실패 시 자동 롤백).

**주의**:
  - 보컬 스템이 아직 전체 카탈로그에 없음 (약 30곡만, 2026-07-15 기준) → m9/m11은 대부분 스킵됨.
  - m6(valence) 추출은 이 환경(bandori-playlist-maker 로컬)에서 보통 모델 없어 스킵.
    WSL2 또는 bpm-research 로컬에서만 가능.
  - 환경별 모델 경로 설정: `export ESSENTIA_EMBEDDING_MODEL=/path/to/msd-musicnn-1.pb`
    (자세한 경로는 `bpm-research/topic/20260731_audio_feats_revised/method-6-valence/` 참고).
  - 기존 빈 행은 보강, 이미 값이 있는 행은 건드리지 않음 (멱등).
  - 곡별 예외는 로그하지 않고 스킵 (다른 곡은 계속 진행).

**산출**:
  - `songs_master.csv` 직접 수정 (스냅샷 유지, 실패 시 자동 복원).
  - 로그: 처리 건수, 보강된 값 개수, 스킵 사유.

기타 스크립트들 (`build_master.py`, `merge_audio_feats.py` 등)은 README 생략.
