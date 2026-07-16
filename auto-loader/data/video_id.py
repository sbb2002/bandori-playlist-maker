"""Pure-function helper for extracting a YouTube video_id from a URL.

Standard-library only. See docs/PRD.md §6 and the document-archive branch's
archive/reports/2026-07-10-data-team-lead-ticket-design.md §⑤ (ticket 2).

Confirmed input format (bandori-song-sorter/src/content/cluster/songs_full.csv,
660 rows, 2026-07-10 measurement): every row is
``https://youtu.be/<11-char video_id>`` with no exceptions. This module treats
that as the primary format but also defensively accepts:

- ``https://youtu.be/<id>?si=...``          (youtu.be with query params)
- ``https://www.youtube.com/watch?v=<id>``  (canonical long-form URL)
- ``https://www.youtube.com/watch?v=<id>&list=...`` (extra query params)
- ``https://www.youtube.com/embed/<id>``     (embed form)
- ``m.youtube.com`` / bare ``youtube.com`` (no ``www.``) host variants

Anything else raises ``ValueError`` — this function never returns ``None``,
so callers cannot accidentally propagate a missing id.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTU_BE_HOSTS = {"youtu.be"}
_YOUTUBE_COM_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com"}


def extract_video_id(url: str) -> str:
    """Extract the 11-character YouTube video id from ``url``.

    Args:
        url: A YouTube URL (``youtu.be/...`` or ``youtube.com/watch?v=...``).

    Returns:
        The 11-character video id.

    Raises:
        ValueError: If ``url`` is not a string, is empty/blank, is not a
            recognizable YouTube URL, or the extracted id is not exactly
            11 characters of ``[A-Za-z0-9_-]``. Never returns ``None``.
    """
    if not isinstance(url, str):
        raise ValueError(f"url must be a string, got {type(url).__name__}")

    stripped = url.strip()
    if not stripped:
        raise ValueError("url must not be empty")

    parsed = urlparse(stripped)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    video_id: str | None = None

    if host in _YOUTU_BE_HOSTS:
        path = parsed.path.lstrip("/")
        video_id = path.split("/")[0] if path else None
    elif host in _YOUTUBE_COM_HOSTS:
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            values = qs.get("v")
            video_id = values[0] if values else None
        elif parsed.path.startswith("/embed/"):
            rest = parsed.path[len("/embed/"):]
            video_id = rest.split("/")[0] if rest else None
        else:
            raise ValueError(f"Unrecognized YouTube URL path: {url!r}")
    else:
        raise ValueError(f"Not a YouTube URL (unrecognized host {host!r}): {url!r}")

    if not video_id:
        raise ValueError(f"Could not locate a video id in URL: {url!r}")

    if not _VIDEO_ID_RE.match(video_id):
        raise ValueError(
            f"Extracted video id {video_id!r} is not 11 characters of "
            f"[A-Za-z0-9_-] (from URL: {url!r})"
        )

    return video_id
