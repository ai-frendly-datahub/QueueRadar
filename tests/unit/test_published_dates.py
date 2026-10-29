"""feedparser *_parsed is UTC. time.mktime must not shift it under TZ=Asia/Seoul."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from queueradar.collector import _extract_datetime
from queueradar.models import Article, Source
from queueradar.storage import RadarStorage


# 2026-10-28 15:00:00 UTC. Wednesday, day 301 of a non-leap year.
_UTC_STRUCT = time.struct_time((2026, 10, 28, 15, 0, 0, 2, 301, 0))


def test_feedparser_struct_stores_1500_utc_under_asia_seoul(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TZ", "Asia/Seoul")
    time.tzset()
    try:
        shifted = datetime.fromtimestamp(time.mktime(_UTC_STRUCT), tz=UTC)
        assert shifted == datetime(2026, 10, 28, 6, 0, tzinfo=UTC)

        source = Source(name="Queue Feed", type="rss", url="https://example.com/feed.xml")
        published = _extract_datetime({"published_parsed": _UTC_STRUCT}, source)
        assert published == datetime(2026, 10, 28, 15, 0, tzinfo=UTC)

        storage = RadarStorage(tmp_path / "radar.duckdb")
        try:
            storage.upsert_articles(
                [
                    Article(
                        title="Wait",
                        link="https://example.com/item",
                        summary="summary",
                        published=published,
                        source=source.name,
                        category="queue",
                    )
                ]
            )
            row = storage.conn.execute("SELECT published FROM articles").fetchone()
            assert row is not None
            assert row[0] == datetime(2026, 10, 28, 15, 0, tzinfo=UTC).replace(tzinfo=None)
            loaded = storage.recent_articles("queue", days=3650)
            assert loaded[0].published == datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
        finally:
            storage.close()
    finally:
        monkeypatch.undo()
        time.tzset()
