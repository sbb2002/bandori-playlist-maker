# src/scripts/ — 데이터팀 소유 (가공 스크립트·운영 툴)

## 작성규칙

1. **표준 라이브러리만** 사용한다 — venv 없이 `python src/scripts/...` 로 바로 실행 가능해야
   한다. 외부 의존이 필요하면 부장 결재를 먼저 받는다.
2. 모든 모듈은 짝이 되는 `test_*.py` 단위 테스트를 같은 폴더에 둔다. 실행:
   `python -m unittest discover -s src/scripts -p "test_*.py"` (하위 폴더는 개별 실행).
3. 산출 데이터는 repo 루트 `data/`에 쓴다 (멱등 — 재실행 시 덮어쓰기). `data/` 원본 소스는
   외부 레포 `bandori-song-sorter`이며 읽기 전용이다.
4. 경로는 `Path(__file__)` 기준으로 계산한다 (cwd 무가정). repo 루트까지의 `.parent` 단수는
   파일 깊이에 따라 다르므로, 각 파일에서 직접 계산하고 단계별 주석을 남긴다
   (`data/build_master.py` 상단 예 참조).
5. 코드설계팀은 `data/camelot.py`·`data/video_id.py`를 **읽기 전용 import**만 허용
   (architecture.md cross-team import 규칙). 이 폴더 파일 편집은 데이터팀만.

## 주의

- `token_gate.py`(트랜스크립트 집계)는 **폐기 예고** 상태 — 세션 수치를 신뢰하지 말 것.
  MCP 관찰 도구로 전환 예정: document-archive 브랜치 `archive/last-papers/reports/2026-07-10-token-gate-mcp-transition.md`.
