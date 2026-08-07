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
LYRIC_CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "lyric_impressions.json"


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
) -> Path | None:
    """`data` 브랜치의 파일 1건을 fetch해 캐시하는 공통 로직(`ensure_songs_csv`/`ensure_lyric_json` 공유).

    `required=False`면 원격 fetch 실패 + 캐시 없음 상황에서 예외 대신 `None`을 반환한다(가사
    임베딩 자산은 프로토타입 성격이라 없어도 앱 기동 자체는 계속돼야 함 — songs_master.csv와
    달리 필수 아님).
    """
    if env_override:
        return Path(env_override)

    if cache_path.exists() and not force:
        return cache_path

    url = _raw_url(repo, branch, filename)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        resp = http.get(url)
        resp.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
        logger.info("%s 원격 fetch 성공(%s@%s, %d bytes).", filename, repo, branch, len(resp.content))
        return cache_path
    except Exception as exc:  # noqa: BLE001 — 네트워크 실패는 캐시 폴백으로 흡수
        if cache_path.exists():
            logger.warning("%s 원격 fetch 실패(%r) — 기존 캐시로 계속 서빙.", filename, exc)
            return cache_path
        if not required:
            logger.warning("%s 원격 fetch 실패(%r)이고 캐시도 없음 — 이 자산 없이 계속 진행.", filename, exc)
            return None
        raise RuntimeError(
            f"{filename} 원격 fetch 실패({exc!r})이고 로컬 캐시도 없습니다: {url}"
        ) from exc
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
) -> Path:
    """`data` 브랜치의 songs_master.csv를 fetch해 `cache_path`에 캐시하고 그 경로를 반환한다.

    - `SONGS_CSV` env가 설정돼 있으면(로컬 개발 override) 원격 fetch 없이 즉시 그 경로를 반환한다.
    - fetch 성공: `cache_path`에 write-through 후 반환.
    - fetch 실패(네트워크·4xx·5xx): `cache_path`가 이미 있으면 그대로 반환(경고 로그, stale 캐시로
      계속 서빙 — 완전 중단보다 낫다). 캐시도 없으면(최초 기동 + 원격 실패) 예외를 올린다.
    - `force=False`이고 캐시가 이미 있으면 재요청 없이 그대로 반환(최초 1회만 fetch; 주기 리프레시는
      호출측이 `force=True`로 명시).
    """
    path = _ensure_data_file(
        filename="songs_master.csv", cache_path=cache_path,
        env_override=os.environ.get("SONGS_CSV"),
        force=force, repo=repo, branch=branch, timeout=timeout, client=client,
        required=True,
    )
    assert path is not None  # required=True라 None이 아님(mypy용 명시)
    return path


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
    없거나 원격 fetch가 실패하면(캐시도 없으면) `None`을 반환한다(songs_master.csv와 달리
    필수 아님 — 없으면 selection.py가 가사 유사도 타이브레이크를 자동으로 건너뜀).
    """
    return _ensure_data_file(
        filename="lyric_impressions.json", cache_path=cache_path,
        env_override=os.environ.get("LYRIC_EMBEDDINGS_JSON"),
        force=force, repo=repo, branch=branch, timeout=timeout, client=client,
        required=False,
    )
