# tools (bandori-playlist-maker)

> **브랜치 범위**: 사람이 로컬에서 수동 트리거하는 반자동 운영 툴 전용 **단일 상시 재사용
> 브랜치**다(`data`·`document-archive`·`research`와 동일한 패턴). `main`(배포 앱 소스)에는
> **머지하지 않는다** — 직접 push, PR 없음. 상세 정책은 `main`의 `git-rules.md` "tools" 절
> 참조.

## 툴 구성

브랜치 루트에 툴 하나당 이름 있는 폴더 하나를 둔다. 각 폴더 안에 그 툴의 사용법 `README.md`를
따로 둔다.

| 폴더 | 툴 | 설명 |
|---|---|---|
| [`auto-loader/`](auto-loader/README.md) | 신곡 오토로더 | 형제 프로젝트(`bandori-song-sorter`)에 반영된 신곡을 감별·다운로드·분석해 `data` 브랜치에 자동 반영 |

새 툴을 추가할 때도 새 git 브랜치를 파지 않고, 이 브랜치 루트에 새 폴더를 추가하는 것으로
시작한다.
