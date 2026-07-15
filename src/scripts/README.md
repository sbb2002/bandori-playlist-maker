# src/scripts/ — 신곡 오토로더 (tools 브랜치)

> **브랜치 범위**: 이 브랜치(`tools`)는 사람이 로컬에서 수동 트리거하는 운영 툴만 담는다
> (2026-07-15 `feature/song-autoloader` → `tools` 정식 승격). `main`(배포 앱 소스)에는
> **머지하지 않는다** — 앱 소스·문서 등 이 툴 구동에 불필요한 파일은 이 브랜치에 두지 않는다.
> 산출 데이터는 `data` 단일 브랜치로 자동 커밋·푸시한다(PR 없음, `data`도 `main`에 병합되지
> 않는 독립 브랜치). 공유 모듈(`data/*`)이 `main`에서 바뀌면 필요 시 이 브랜치를 `main`에
> rebase해 최신화한다.

## 작성규칙

1. **표준 라이브러리만** 사용한다 — venv 없이 바로 실행 가능해야 한다.
   - **오디오 스택 예외**: 오디오 분석 계열(`data/extract_full_energy.py`,
     `data/extract_temporal_intensity.py`, `data/build_energy_full.py`, `autoloader/`)은
     numpy/librosa/soundfile/scipy(+다운로드는 yt-dlp, ffmpeg 폴백 imageio_ffmpeg)를 쓴다.
     오디오 스택이 설치된 env에서만 실행하며, 단위 테스트는 오디오·네트워크 없이 도는
     순수 로직만 다룬다.
2. 모든 모듈은 짝이 되는 `test_*.py` 단위 테스트를 같은 폴더에 둔다. 실행:
   `python -m unittest discover -s src/scripts -p "test_*.py"` (하위 폴더는 개별 실행).
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
python src/scripts/autoloader/run_autoloader.py --dry     # 검증(파일 미변경)
python src/scripts/autoloader/run_autoloader.py --repo-root <data브랜치 워크트리>
                                                             # data/ 반영 + data 브랜치 자동 커밋·푸시
python src/scripts/autoloader/run_autoloader.py --no-git   # data/ 반영만, 커밋·푸시 생략
python src/scripts/autoloader/run_autoloader.py --soft     # 부분 wav 환경 긴급 반영(아래)
```

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
