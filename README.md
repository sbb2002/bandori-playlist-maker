# data (bandori-playlist-maker)

> **브랜치 범위**: 처리된 곡 데이터셋 전용 **단일 상시 재사용 브랜치**다(`tools`·
> `document-archive`·`research`와 동일한 패턴). 이 브랜치에는 `data/`와 이 문서들 외에는
> **아무것도 두지 않는다** — 앱 소스·문서 등은 전부 `main`에만 있다. `main`(배포 앱 소스)에는
> **머지하지 않는다**: 직접 push, PR 없음. 상세 정책은 `main`의 `git-rules.md` "data" 절 참조.

## 누가 이 데이터를 쓰는가

- **소비**: 배포된 백엔드(`main`의 `src/backend/app/repo/remote_source.py`)가 런타임에
  `raw.githubusercontent.com`으로 `data/songs_master.csv`만 직접 fetch한다(기동 시 + 주기
  리프레시). `main`은 `data/` 디렉터리 자체를 갖지 않는다 — 데이터가 바뀔 때마다 `main`을
  재배포(=프리징)하지 않기 위한 의도적 분리.
- **생산**: `tools` 브랜치의 [`auto-loader/`](https://github.com/sbb2002/bandori-playlist-maker/tree/tools/auto-loader)가
  신곡을 감별·다운로드·분석해 이 브랜치의 `data/`에 자동 커밋·푸시한다(PR 없음).

## data/ 파일 구성

| 파일 | 역할 |
|---|---|
| `songs_master.csv` | canonical — 전역 `idx` 조인, 배포 백엔드가 읽는 유일한 파일 |
| `songs_full.csv` | 형제 프로젝트 원본 스냅샷(통째 복사) |
| `song_features_with_proxies.csv` | mood/energy proxy 피처 |
| `full_audio_features.csv` | 전곡 서브피처(재추출) |
| `temporal_intensity.csv` | 시간분절 강도(`i_*`) |
| `audio_map.json` | bpm/energy/shape 등 보조 피처 |
| `feature_norms.json` / `energy_full_norm.json` / `intensity_norm.json` | 오토로더의 동결(frozen) 정규화 상수 |
| `legacy/` | 구버전 스냅샷(참고용) |

## 버전 관리

이 브랜치는 `main`과 별개의 데이터 전용 버전 체계를 [`versionlog.md`](versionlog.md)로
관리한다(Major=구조 개편, Minor=컬럼 변경, Patch=신곡 추가). 데이터를 바꿀 때마다 함께 갱신한다.
