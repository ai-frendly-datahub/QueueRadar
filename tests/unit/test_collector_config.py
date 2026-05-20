from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from queueradar.collector import collect_sources, filter_articles_by_source_scope
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


def test_source_scope_filter_keeps_only_title_level_queue_signals() -> None:
    source = Source(
        name="Blooloop",
        type="rss",
        url="https://example.com/feed",
        config={
            "scope_filter": {
                "mode": "include_any_keyword",
                "fields": ["title"],
                "include_keywords": ["theme park", "coaster", "Disneyland"],
            }
        },
    )
    scoped = _article("Blooloop")
    scoped.title = "New coaster opens at Disneyland"
    off_scope = _article("Blooloop")
    off_scope.title = "Museum of Contemporary Art Detroit reopens"
    off_scope.summary = "Theme park industry newsletter footer text"

    filtered = filter_articles_by_source_scope([scoped, off_scope], [source])

    assert filtered == [scoped]


def test_collect_sources_applies_source_scope_filter() -> None:
    source = Source(
        name="Blooloop",
        type="rss",
        url="https://example.com/feed",
        config={
            "scope_filter": {
                "mode": "include_any_keyword",
                "fields": ["title"],
                "include_keywords": ["coaster"],
            }
        },
    )
    scoped = _article("Blooloop")
    scoped.title = "New coaster opens"
    off_scope = _article("Blooloop")
    off_scope.title = "Museum reopening"

    mock_breaker = Mock()
    mock_breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    mock_manager = Mock()
    mock_manager.get_breaker.return_value = mock_breaker
    fake_health = Mock()
    fake_health.is_disabled.return_value = False

    with (
        patch("queueradar.collector.get_circuit_breaker_manager", return_value=mock_manager),
        patch("queueradar.collector.CrawlHealthStore", return_value=fake_health),
        patch("queueradar.collector._collect_single", return_value=[scoped, off_scope]),
    ):
        articles, errors = collect_sources(
            [source],
            category="queue",
            max_workers=1,
            min_interval_per_host=0.0,
        )

    assert articles == [scoped]
    assert errors == []
