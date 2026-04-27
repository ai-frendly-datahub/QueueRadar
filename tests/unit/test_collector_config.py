from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from queueradar.collector import collect_sources
from queueradar.models import Article, Source


def _article(source: str) -> Article:
    return Article(
        title=f"{source} item",
        link=f"https://example.com/{source}",
        summary="summary",
        published=datetime(2026, 4, 21, tzinfo=UTC),
        source=source,
        category="queue",
    )


def test_collect_sources_skips_disabled_and_health_disabled_sources() -> None:
    active = Source(name="Active", type="rss", url="https://example.com/feed")
    disabled = Source(name="Disabled", type="rss", url="https://example.com/off", enabled=False)
    health_disabled = Source(name="HealthDisabled", type="rss", url="https://example.com/health")

    mock_breaker = Mock()
    mock_breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    mock_manager = Mock()
    mock_manager.get_breaker.return_value = mock_breaker
    fake_session = Mock()
    fake_health = Mock()
    fake_health.is_disabled.side_effect = lambda name: name == "HealthDisabled"

    with (
        patch("queueradar.collector.get_circuit_breaker_manager", return_value=mock_manager),
        patch("queueradar.collector._create_session", return_value=fake_session),
        patch("queueradar.collector.CrawlHealthStore", return_value=fake_health),
        patch("queueradar.collector._collect_single", return_value=[_article("Active")]) as mock_single,
    ):
        articles, errors = collect_sources(
            [active, disabled, health_disabled],
            category="queue",
            max_workers=1,
        )

    assert [article.source for article in articles] == ["Active"]
    assert errors == []
    assert mock_single.call_count == 1
