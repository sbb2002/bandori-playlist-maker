# src/scripts/ — 데이터팀 소유 (가공 스크립트·운영 툴)

## 작성규칙

1. **표준 라이브러리만** 사용한다 — venv 없이 `python src/scripts/...` 로 바로 실행 가능해야
   한다. 외부 의존이 필요하면 부장 결재를 먼저 받는다.
   - **오디오 스택 예외**: 오디오 분석 계열은 numpy/librosa/soundfile/scipy(+다운로드는
     yt-dlp, ffmpeg 폴백 imageio_ffmpeg)를 쓴다 — `data/extract_full_energy.py`,
     `data/extract_temporal_intensity.py`, `data/build_energy_full.py`, `autoloader/`(아래).
     오디오 스택이 설치된 env에서만 실행하며, 단위 테스트는 오디오·네트워크 없이 도는
     순수 로직만 다룬다.
2. 모든 모듈은 짝이 되는 `test_*.py` 단위 테스트를 같은 폴더에 둔다. 실행:
   `python -m unittest discover -s src/scripts -p "test_*.py"` (하위 폴더는 개별 실행).
3. 산출 데이터는 repo 루트 `data/`에 쓴다 (멱등 — 재실행 시 덮어쓰기). `data/` 원본 소스는
   외부 레포 `bandori-song-sorter`이며 읽기 전용이다.
4. 경로는 `Path(__file__)` 기준으로 계산한다 (cwd 무가정). repo 루트까지의 `.parent` 단수는
   파일 깊이에 따라 다르므로, 각 파일에서 직접 계산하고 단계별 주석을 남긴다
   (`data/build_master.py` 상단 예 참조).
5. 코드설계팀은 `data/camelot.py`·`data/video_id.py`를 **읽기 전용 import**만 허용
   (architecture.md cross-team import 규칙). 이 폴더 파일 편집은 데이터팀만.

## autoloader/ — 신곡 오토로더 (로컬 원커맨드)

형제 프로젝트(`bandori-song-sorter`)의 semiauto-loader를 이 프로젝트 데이터 스키마에 맞게
재구성한 신곡 반영 파이프라인. **감지(RSS·Telegram)는 형제 Actions가 전담**하고, 여기서는
형제 origin/main에 반영된 곡과 우리 `data/songs_master.csv`의 차이만 처리한다.

```
python src/scripts/autoloader/run_autoloader.py --dry   # 검증(파일 미변경)
python src/scripts/autoloader/run_autoloader.py         # data/ 반영(git 없음)
python src/scripts/autoloader/run_autoloader.py --repo-root <data브랜치 워크트리> --git
```

- 흐름: 감별(`sources.py`) → yt-dlp 다운로드(`fetch_new.py`, 집 IP 전제) → 45s excerpt
  특징(`excerpt_features.py`, 형제 로직 벤더링) + 전곡 서브피처/시간분절 강도(기존
  `data/extract_*` 모듈 재사용) → **동결 norm**(`norms.py`)으로 proxy·energy_full·i_* 산출 →
  `data/` 6파일 원자 반영(`merge_data.py`, 실패 시 전체 롤백).
- **동결 norm 원칙**: 기존 658행은 바이트 불변, 신곡만 원래 분포(원시 660곡 기준)에
  대입한다. 동결 상수는 `data/feature_norms.json`·`data/energy_full_norm.json`·
  `data/intensity_norm.json`으로 영속화하며, 최초 구축 시 기존 행 재계산 대조로 검증한다
  (proxy 최대오차 0, energy_full exact 658/658 확인 — 2026-07-15).
- 데이터 반영은 `git-rules.md`의 `data` 단일 브랜치에 커밋하되, **main 머지는 소유자가
  PR로 수행한다**(CLAUDE.md Working agreement — `data` 브랜치의 "바로 머지" 규칙은
  PR 자동머지 Actions 도입 후 적용).
- 재실행 안전: video_id 기준 감별이라 멱등, 실패 곡은 다음 실행에서 자동 재시도.

## 주의

- `token_gate.py`(트랜스크립트 집계)는 **폐기 예고** 상태 — 세션 수치를 신뢰하지 말 것.
  MCP 관찰 도구로 전환 예정: document-archive 브랜치 `archive/reports/2026-07-10-token-gate-mcp-transition.md`.
