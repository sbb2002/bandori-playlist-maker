"""`data` 브랜치의 songs_master.csv를 런타임에 원격 fetch — main에는 data/가 없다.

`main`은 앱 소스만 배포하고(`render.yaml` autoDeploy on main push), 데이터는 별도 `data` 브랜치에서
오토로더가 PR 없이 상시 커밋·푸시한다(git-rules.md). 데이터가 바뀔 때마다 `main`을 재배포하면(=
프리징) 목적에 안 맞으므로, 배포된 backend가 기동 시 + 주기적으로 GitHub에서 `data` 브랜치의
`songs_master.csv`만 직접 읽어온다(리포는 public — 인증 불필요, `raw.githubusercontent.com`).

로컬 개발·테스트는 `SONGS_CSV` env(`song_repo._resolve_path`가 이미 지원)를 그대로 쓰면 원격 fetch를
건너뛴다.

2026-08-17 인시던트: `raw.githubusercontent.com`이 무인증 요청에 429(Too Many Requests)를 반환해
기동 시 fetch가 전부 실패 + 로컬 캐시도 없어(Render free tier는 재시작마다 디스크 초기화) 백엔드가
아예 뜨지 못했다. 이후 재시도(`RETRY_ATTEMPTS`)와, 그래도 실패하면 리포에 번들된 스냅샷
(`fallback/songs_master.csv`)으로 최소 기동은 계속되게 하는 안전망을 추가했다.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger("setlist_maker")

DEFAULT_REPO = "sbb2002/bandori-playlist-maker"
DEFAULT_BRANCH = "data"
DEFAULT_TIMEOUT = 10.0
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.5  # 시도 n번째마다 n * 이 값만큼 대기(1.5s, 3s, ...).
CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "songs_master.csv"
LYRIC_CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "lyric_impressions.json"
# 원격 fetch가 재시도 끝에 실패하고 로컬 캐시도 없을 때 쓰는 최후의 보루 — 리포에 커밋된
# songs_master.csv 스냅샷(배포 시 함께 실림). 최신 곡은 반영 안 돼 있을 수 있지만 "아예 안 뜸"보다
# 낫다. 신곡 백필 때마다 자동 갱신되지는 않으므로 가끔 수동으로 최신화 필요.
FALLBACK_SONGS_CSV = Path(__file__).resolve().parent / "fallback" / "songs_master.csv"


def _raw_url(repo: str, branch: str, filename: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/data/{filename}"


def _ensure_data_file(
    *,
    filename: str,
    cache_path: Path,
    env_override: str | None,
    force: bool,
    repo: str,
    branch: str,
    timeout: float,
    client: httpx.Client | None,
    required: bool,
    fallback_path: Path | None = None,
    attempts: int = RETRY_ATTEMPTS,
    backoff_seconds: float = RETRY_BACKOFF_SECONDS,
) -> tuple[Path | None, bool, str | None]:
    """`data` 브랜치의 파일 1건을 fetch해 캐시하는 공통 로직(`ensure_songs_csv`/`ensure_lyric_json` 공유).

    반환값: `(path, degraded, reason)`. `degraded=True`면 이번 호출이 신선한 원격 데이터가 아니라
    stale 캐시나 번들 fallback으로 대체됐다는 뜻(호출측이 알림 여부를 판단하는 신호) — `reason`은
    그때만 채워진다.

    `required=False`면 원격 fetch가 재시도 끝에 실패 + 캐시·fallback도 없는 상황에서 예외 대신
    `(None, True, reason)`을 반환한다(가사 임베딩 자산은 프로토타입 성격이라 없어도 앱 기동 자체는
    계속돼야 함 — songs_master.csv와 달리 필수 아님).
    """
    if env_override:
        return Path(env_override), False, None

    if cache_path.exists() and not force:
        return cache_path, False, None

    url = _raw_url(repo, branch, filename)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    last_exc: Exception | None = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                resp = http.get(url)
                resp.raise_for_status()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(resp.content)
                logger.info(
                    "%s 원격 fetch 성공(%s@%s, %d bytes, 시도 %d/%d).",
                    filename, repo, branch, len(resp.content), attempt, attempts,
                )
                return cache_path, False, None
            except Exception as exc:  # noqa: BLE001 — 재시도 소진까지는 흡수
                last_exc = exc
                logger.warning(
                    "%s 원격 fetch 시도 %d/%d 실패(%r).", filename, attempt, attempts, exc
                )
                if attempt < attempts:
                    time.sleep(backoff_seconds * attempt)

        reason = f"{attempts}회 재시도 후 {filename} 원격 fetch 실패({last_exc!r}): {url}"
        if cache_path.exists():
            logger.warning("%s — 기존 캐시로 계속 서빙.", reason)
            return cache_path, True, reason
        if fallback_path is not None and fallback_path.exists():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(fallback_path.read_bytes())
            logger.warning("%s — 번들 fallback 스냅샷으로 계속 서빙(%s).", reason, fallback_path)
            return cache_path, True, reason
        if not required:
            logger.warning("%s — 캐시·fallback도 없음, 이 자산 없이 계속 진행.", reason)
            return None, True, reason
        raise RuntimeError(reason) from last_exc
    finally:
        if owns_client:
            http.close()


def ensure_songs_csv(
    cache_path: Path = CACHE_PATH,
    *,
    force: bool = False,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> tuple[Path, bool, str | None]:
    """`data` 브랜치의 songs_master.csv를 fetch해 `cache_path`에 캐시하고 `(경로, degraded, 사유)`를 반환한다.

    - `SONGS_CSV` env가 설정돼 있으면(로컬 개발 override) 원격 fetch 없이 즉시 그 경로를 반환한다.
    - fetch 성공: `cache_path`에 write-through 후 `(path, False, None)` 반환.
    - fetch 실패(네트워크·4xx·5xx, `RETRY_ATTEMPTS`회 재시도 소진): `cache_path`가 이미 있으면 그대로
      반환(경고 로그, stale 캐시로 계속 서빙). 캐시도 없으면 리포에 번들된 `FALLBACK_SONGS_CSV`
      스냅샷으로 대체. 두 폴백 중 하나라도 성공하면 `(path, True, reason)`을 반환한다(신선하지 않은
      데이터로 기동했다는 신호 — 호출측이 알림을 보낼지 판단).
    - fallback 스냅샷조차 없으면(이론상 없어야 함) 예외를 올린다(필수 자산).
    - `force=False`이고 캐시가 이미 있으면 재요청 없이 그대로 반환(최초 1회만 fetch; 주기 리프레시는
      호출측이 `force=True`로 명시).
    """
    path, degraded, reason = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path,
        env_override=os.environ.get("SONGS_CSV"),
        force=force, repo=repo, branch=branch, timeout=timeout, client=client,
        required=True, fallback_path=FALLBACK_SONGS_CSV,
    )
    assert path is not None  # required=True라 None이 아님(mypy용 명시)
    return path, degraded, reason


def ensure_lyric_json(
    cache_path: Path = LYRIC_CACHE_PATH,
    *,
    force: bool = False,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> Path | None:
    """`data` 브랜치의 lyric_impressions.json을 fetch해 캐시하고 그 경로를 반환한다.

    가사 감상 임베딩 프로토타입용 보조 자산 — `LYRIC_EMBEDDINGS_JSON` env로 로컬 override,
    없거나 원격 fetch가 재시도 끝에 실패하면(캐시도 없으면) `None`을 반환한다(songs_master.csv와
    달리 필수 아님 — 없으면 selection.py가 가사 유사도 타이브레이크를 자동으로 건너뜀). fallback
    스냅샷은 두지 않는다 — 프로토타입 자산이라 stale보다는 없는 편이 낫다는 판단.
    """
    path, _degraded, _reason = _ensure_data_file(
        filename="lyric_impressions.json", cache_path=cache_path,
        env_override=os.environ.get("LYRIC_EMBEDDINGS_JSON"),
        force=force, repo=repo, branch=branch, timeout=timeout, client=client,
        required=False,
    )
    return path
