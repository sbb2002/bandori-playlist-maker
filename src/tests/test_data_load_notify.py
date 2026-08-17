"""`_load_current_songs`가 degraded fetch(stale 캐시·번들 fallback) 시 알림 콜백을 호출하는지 검증.

실제 네트워크·Telegram 전송은 타지 않는다 — `remote_source.ensure_songs_csv`를 monkeypatch한다.
"""

from __future__ import annotations

from pathlib import Path

from app import main as main_module

_FIXTURE_CSV = Path(__file__).parent / "fixtures" / "songs_master.csv"


def test_notify_called_when_fetch_degraded(monkeypatch):
    calls = []

    def fake_ensure_songs_csv(*, force=False):
        return _FIXTURE_CSV, True, "3회 재시도 후 songs_master.csv 원격 fetch 실패(가짜 사유)"

    monkeypatch.setattr(main_module.remote_source, "ensure_songs_csv", fake_ensure_songs_csv)
    monkeypatch.setattr(main_module.remote_source, "ensure_lyric_json", lambda *, force=False: None)

    songs = main_module._load_current_songs(
        notify=lambda title, body: calls.append((title, body))
    )

    assert len(songs) > 0
    assert len(calls) == 1
    title, body = calls[0]
    assert "저하" in title
    assert "재시도" in body


def test_notify_not_called_when_fetch_fresh(monkeypatch):
    calls = []

    def fake_ensure_songs_csv(*, force=False):
        return _FIXTURE_CSV, False, None

    monkeypatch.setattr(main_module.remote_source, "ensure_songs_csv", fake_ensure_songs_csv)
    monkeypatch.setattr(main_module.remote_source, "ensure_lyric_json", lambda *, force=False: None)

    main_module._load_current_songs(notify=lambda title, body: calls.append((title, body)))

    assert calls == []
