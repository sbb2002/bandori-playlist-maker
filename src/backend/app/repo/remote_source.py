"""`data` 브랜치의 songs_master.csv를 런타임에 원격 fetch — main에는 data/가 없다.

`main`은 앱 소스만 배포하고(`render.yaml` autoDeploy on main push), 데이터는 별도 `data` 브랜치에서
오토로더가 PR 없이 상시 커밋·푸시한다(git-rules.md). 데이터가 바뀔 때마다 `main`을 재배포하면(=
프리징) 목적에 안 맞으므로, 배포된 backend가 기동 시 + 주기적으로 GitHub에서 `data` 브랜치의
`songs_master.csv`만 직접 읽어온다(리포는 public — 인증 불필요, `raw.githubusercontent.com`).

로컬 개발·테스트는 `SONGS_CSV` env(`song_repo._resolve_path`가 이미 지원)를 그대로 쓰면 원격 fetch를
건너뛴다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger("setlist_maker")

DEFAULT_REPO = "sbb2002/bandori-playlist-maker"
DEFAULT_BRANCH = "data"
DEFAULT_TIMEOUT = 10.0
CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "songs_master.csv"


def _raw_url(repo: str, branch: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/data/songs_master.csv"


def ensure_songs_csv(
    cache_path: Path = CACHE_PATH,
    *,
    force: bool = False,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> Path:
    """`data` 브랜치의 songs_master.csv를 fetch해 `cache_path`에 캐시하고 그 경로를 반환한다.

    - `SONGS_CSV` env가 설정돼 있으면(로컬 개발 override) 원격 fetch 없이 즉시 그 경로를 반환한다.
    - fetch 성공: `cache_path`에 write-through 후 반환.
    - fetch 실패(네트워크·4xx·5xx): `cache_path`가 이미 있으면 그대로 반환(경고 로그, stale 캐시로
      계속 서빙 — 완전 중단보다 낫다). 캐시도 없으면(최초 기동 + 원격 실패) 예외를 올린다.
    - `force=False`이고 캐시가 이미 있으면 재요청 없이 그대로 반환(최초 1회만 fetch; 주기 리프레시는
      호출측이 `force=True`로 명시).
    """
    env_path = os.environ.get("SONGS_CSV")
    if env_path:
        return Path(env_path)

    if cache_path.exists() and not force:
        return cache_path

    url = _raw_url(repo, branch)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        resp = http.get(url)
        resp.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
        logger.info("songs_master.csv 원격 fetch 성공(%s@%s, %d bytes).", repo, branch, len(resp.content))
        return cache_path
    except Exception as exc:  # noqa: BLE001 — 네트워크 실패는 캐시 폴백으로 흡수
        if cache_path.exists():
            logger.warning("songs_master.csv 원격 fetch 실패(%r) — 기존 캐시로 계속 서빙.", exc)
            return cache_path
        raise RuntimeError(
            f"songs_master.csv 원격 fetch 실패({exc!r})이고 로컬 캐시도 없습니다: {url}"
        ) from exc
    finally:
        if owns_client:
            http.close()
