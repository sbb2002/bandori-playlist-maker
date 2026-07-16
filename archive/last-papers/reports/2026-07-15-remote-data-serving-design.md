# 2026-07-15 — 원격 데이터 서빙 설계 (데이터 머지 재배포 프리징 제거)

> **상태: 설계 스펙(구현 전).** 다음 전용 작업(feature 브랜치)의 입력 문서다. 사용자 확정:
> "이번엔 설계만, 구현은 다음 전용 작업"(2026-07-15).

## 1. 문제

현재 백엔드는 곡 목록을 **프로세스 기동 시 1회만** 적재한다:

- `src/backend/app/main.py:268` — `app.state.songs = load_songs()` (`create_app()` 안).
- 모든 요청은 `request.app.state.songs`(메모리 상주 사본)를 읽는다(`api/routes.py`).

따라서 **새 데이터는 프로세스 재시작(=재배포) 후에만** 앱에 반영된다. `render.yaml`은
`autoDeploy: true`라 `main` push마다 재배포되고, 무료 플랜은 "15분 유휴 → 첫 요청 콜드스타트
~50s"다. 즉 **데이터를 반영하려고 `main`에 머지하면 그때마다 재배포·콜드스타트 프리징**이
발생한다.

앱·핫픽스·패치 머지는 어차피 간헐적으로 일어나지만(그건 앱 변경이라 재배포가 당연),
**데이터 반영 때문에 생기는 재배포만** 없애는 것이 목표다.

## 2. 목표와 제약

- **목표**: `data` 브랜치 갱신 → **재배포 없이** 라이브 앱에 반영.
- `data` 브랜치는 새 워크플로대로 **`main`에 머지하지 않는다**(신곡 오토로더가 `data`
  브랜치에 커밋·PR하지만, 프리징을 없애려면 `main` 머지 자체를 피해야 함 → 백엔드가 `data`
  브랜치를 직접 소비).
- 서빙에 필요한 데이터는 **`songs_master.csv` 하나뿐**(`song_repo.load_songs`만 소비. 나머지
  `full_audio_features`/`temporal_intensity` 등은 오토로더 전용). → 원격화 표면이 작다.
- 외부 호출이 생기므로 **헥사고날 포트/어댑터**(PRD §8, architecture.md)로 감싼다.

## 3. 확인된 사실(설계 근거)

- `httpx`는 이미 백엔드 의존성(groq 어댑터가 사용) → 추가 의존 없음.
- `main.py`에 백그라운드 asyncio 태스크 패턴(`_bg_tasks` set + `create_task` +
  `add_done_callback`)이 이미 있음 → 리프레시 루프에 재사용.
- `song_repo._resolve_path`에 `SONGS_CSV` env override가 이미 있음 → 로컬/번들 폴백 경로.
- `load_songs()`는 적재 시 eligible 풀 분포로 백분위 랭커를 만든다 → **전체 재적재는 전부
  재계산**(부분 갱신 아님)이라 원자적 교체로 안전.
- 레포는 **public** → `raw.githubusercontent.com`은 인증 불필요·API rate limit 무관(CDN).
  (private 전환 시에만 PAT 필요 — 현재 무관.)

## 4. 설계

### 4.1 헥사고날 — SongSource 포트

```
ports/song_source.py        SongSource(Protocol): fetch_csv_text() -> str
adapters/local_song_source.py   LocalFileSongSource(path)     # 파일 읽기(현행/번들 폴백)
adapters/remote_song_source.py  RemoteHttpSongSource(url, cache_path)  # httpx GET + 캐시
```

`main.py`의 composition root에서 env로 어댑터 선택(LLM 포트와 동일 패턴).

### 4.2 song_repo 리팩터(파싱/획득 분리)

- 현 `load_songs(path)` 본문의 **파싱·랭킹 로직**을 순수 함수 `parse_songs(rows) ->
  list[Song]`로 추출(무네트워크·무파일, 단위테스트 대상).
- `load_songs(path)`는 로컬 경로용으로 유지(`parse_songs` 호출). 신규 `load_songs_from_text(text)`
  추가(원격 응답 본문 파싱).

### 4.3 기동(create_app) — 폴백 체인

`SONGS_CSV_URL`이 설정돼 있으면 순서대로 시도, 아니면 현행 로컬:

1. **원격** 1회 fetch → 파싱 → `app.state.songs`.
2. 실패 시 **온디스크 캐시**(직전 성공 본문, 있으면).
3. 그래도 실패 시 **`main` 번들 `data/songs_master.csv`**(항상 존재하는 최후 폴백).

`app.state`에 진단 필드 기록: `songs_source`("remote"/"cache"/"bundled"),
`songs_loaded_at`, `song_count`.

### 4.4 백그라운드 리프레시

- `SONGS_REFRESH_SEC`(기본 900) 간격 asyncio 루프(`_bg_tasks` 재사용, lifespan/shutdown에서
  취소). 매 주기 원격 fetch:
  - 성공 → 파싱 → `app.state.songs`를 **원자적 참조 교체**(단일 스레드 asyncio라 안전) +
    온디스크 캐시 갱신 + 타임스탬프.
  - 실패 → 로그만, **직전 목록 유지**(리트라이 폭주 없음 — 최소 폴백 철학).
- 최적화(선택): 조건부 GET(ETag/If-Modified-Since)로 미변경 시 재파싱 생략.
- 즉시 반영이 필요하면(선택) 보호된 `POST /api/admin/refresh` 엔드포인트로 수동 트리거.

### 4.5 환경변수 / render.yaml

```
SONGS_CSV_URL   = https://raw.githubusercontent.com/sbb2002/bandori-playlist-maker/data/data/songs_master.csv
                  # 브랜치 'data', 경로 'data/songs_master.csv' → 경로에 data가 두 번 나오는 게 정상
SONGS_REFRESH_SEC = 900
# SONGS_CSV(로컬 경로 override)는 개발/폴백용으로 유지
```

- **`main`의 `data/` 폴더는 제거하지 않고 번들 폴백으로 유지**(4.3의 3단계). "Render가 브랜치
  raw를 못 읽는" 드문 상황에서도 앱이 기동 시 번들 사본으로 계속 서빙 → 리트라이 로직 없이도
  안전(사용자 우려 "폴백/리트라이가 과하다"에 대한 최소 답).

### 4.6 관측성

- `/api/health`에 `songs_source`·`songs_loaded_at`·`song_count` 노출(프론트/운영 진단).

## 5. 동작 결과

오토로더 `--git`이 `data` 브랜치에 push → raw URL이 CDN 지연(수초~~1분) 후 새 내용 반영 →
백엔드가 다음 리프레시(≤ `SONGS_REFRESH_SEC`)에 픽업. **`main` 무변경 → 재배포 없음 →
프리징 없음.** 앱·핫픽스 머지로 인한 재배포는 그대로(그건 코드 변경이라 당연).

## 6. 트레이드오프 / 주의

- **반영 지연**: 최대 `SONGS_REFRESH_SEC` + CDN 지연. 데이터 신선도가 초 단위로 중요하지
  않으므로 허용. 급하면 수동 refresh 엔드포인트.
- **무료 플랜 유휴 슬립**: 잠든 동안 리프레시 안 돎 → 깨어날 때 기동 fetch가 최신을 가져오므로
  무해.
- **온디스크 캐시**: Render 무료 파일시스템은 재배포 시 초기화(프로세스 수명 내 유지) →
  캐시는 배포 내에서만 유효, 배포 후 바닥은 번들 사본. 수용 가능.
- **동시성**: 참조 교체는 asyncio 단일 스레드에서 원자적. 교체 중 옛 목록을 읽는 요청도 정상.
- **git-rules `data` 절 재검토 대상**: 현 문서의 "`data`는 매 커밋마다 `main` 머지" 문구는
  이 설계와 상충(그 머지가 프리징의 원인). 구현 채택 시 git-rules `data` 절을 "원격 서빙으로
  소비, `main` 미머지"로 개정 필요. **이 설계는 과거의 'data auto-merge Actions' 아이디어를
  대체**(자동 머지도 재배포를 유발하므로).

## 7. 테스트

- **단위**: `parse_songs(text)` 정확성; 폴백 선택(가짜 SongSource로 실패 주입, 무네트워크);
  원자 교체 후 타임스탬프/카운트.
- **통합**: 가짜 httpx transport가 준비된 CSV 반환 → 리프레시 1주기 교체 검증.
- **수동 E2E**: 로컬에서 `SONGS_CSV_URL`을 실제 data 브랜치 raw URL로 설정→기동→`/api/health`가
  `source=remote`·정확한 곡수 표시 확인. `data` 브랜치에 한 곡 push→리프레시 주기 내 반영 확인.

## 8. 롤아웃

- 전용 `feature/remote-song-source` 브랜치에서 구현 → PR → `main` → **1회 재배포로 활성화**.
  이후 데이터 변경은 재배포를 유발하지 않는다.
- 안전 배포: `SONGS_CSV_URL` **미설정 상태로 머지**(번들 로컬로 폴백 = 현행 동작 유지) →
  Render 대시보드에서 env를 넣는 순간 원격 서빙 활성화. 롤백은 env 제거로 즉시.
- 영향 범위: `song_repo` + `main.py`(composition root + 백그라운드 태스크) +
  신규 ports/adapters + `render.yaml` + 테스트. 모듈 격리로 리스크 낮음.

## 관련

- 결정 배경 대화: 2026-07-15 세션(soft-run 논의에서 파생).
- 오토로더 tool 브랜치 확정: `git-rules.md` "tool/*" 절(PR #32), `src/scripts/README.md`.
- 백엔드 적재 지점: `src/backend/app/main.py:268`, `src/backend/app/repo/song_repo.py`.
