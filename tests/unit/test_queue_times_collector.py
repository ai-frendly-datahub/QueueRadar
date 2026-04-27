from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from queueradar.models import Article, Source
from queueradar.queue_times_collector import (
    _extract_park_id,
    _parse_iso_datetime,
    _ride_to_article,
    collect_queue_times,
)


SAMPLE_API_RESPONSE = {
    "lands": [
        {
            "id": 100,
            "name": "Adventureland",
            "rides": [
                {
                    "id": 1001,
                    "name": "Pirates of the Caribbean",
                    "is_open": True,
                    "wait_time": 45,
                    "last_updated": "2026-03-05T10:30:00.000Z",
                },
                {
                    "id": 1002,
                    "name": "Jungle Cruise",
                    "is_open": False,
                    "wait_time": 0,
                    "last_updated": "2026-03-05T10:30:00.000Z",
                },
            ],
        },
        {
            "id": 200,
            "name": "Tomorrowland",
            "rides": [
                {
                    "id": 2001,
                    "name": "Space Mountain",
                    "is_open": True,
                    "wait_time": 0,
                    "last_updated": "2026-03-05T10:30:00.000Z",
                },
            ],
        },
    ],
    "rides": [],
}


@pytest.mark.unit
class TestExtractParkId:
    def test_standard_url(self) -> None:
        url = "https://queue-times.com/parks/6/queue_times.json"
        assert _extract_park_id(url) == "6"

    def test_large_id(self) -> None:
        url = "https://queue-times.com/parks/334/queue_times.json"
        assert _extract_park_id(url) == "334"

    def test_no_match(self) -> None:
        assert _extract_park_id("https://example.com/data") is None


@pytest.mark.unit
class TestParseIsoDatetime:
    def test_z_suffix(self) -> None:
        dt = _parse_iso_datetime("2026-03-05T10:30:00.000Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.hour == 10

    def test_empty_string(self) -> None:
        assert _parse_iso_datetime("") is None

    def test_invalid_string(self) -> None:
        assert _parse_iso_datetime("not-a-date") is None


@pytest.mark.unit
class TestRideToArticle:
    def test_open_ride_with_wait(self) -> None:
        ride = {
            "id": 42,
            "name": "Test Coaster",
            "is_open": True,
            "wait_time": 30,
            "last_updated": "2026-03-05T12:00:00.000Z",
        }
        article = _ride_to_article(
            ride,
            park_name="Test Park",
            land_name="Area A",
            park_url="https://queue-times.com/en-US/parks/1/queue_times",
            category="queue",
        )
        assert article is not None
        assert "Test Coaster" in article.title
        assert "30 minutes wait" in article.title
        assert "wait time: 30 minutes" in article.summary
        assert "Status: Open" in article.summary
        assert article.source == "Test Park"

    def test_closed_ride(self) -> None:
        ride = {
            "id": 43,
            "name": "Closed Ride",
            "is_open": False,
            "wait_time": 0,
            "last_updated": "2026-03-05T12:00:00.000Z",
        }
        article = _ride_to_article(
            ride,
            park_name="Test Park",
            land_name="Area B",
            park_url="https://example.com",
            category="queue",
        )
        assert article is not None
        assert "Closed" in article.title
        assert "Status: Closed" in article.summary

    def test_empty_name_returns_none(self) -> None:
        ride = {"id": 44, "name": "", "is_open": True, "wait_time": 0}
        result = _ride_to_article(
            ride,
            park_name="Park",
            land_name="Land",
            park_url="https://example.com",
            category="queue",
        )
        assert result is None


@pytest.mark.unit
class TestCollectQueueTimes:
    @patch("queueradar.queue_times_collector.requests.get")
    def test_collects_rides_from_all_lands(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_API_RESPONSE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        source = Source(
            name="Test Park",
            type="api",
            url="https://queue-times.com/parks/6/queue_times.json",
        )
        articles = collect_queue_times(source, category="queue")

        assert len(articles) == 3
        titles = [a.title for a in articles]
        assert any("Pirates of the Caribbean" in t for t in titles)
        assert any("Space Mountain" in t for t in titles)
        assert any("Jungle Cruise" in t for t in titles)

    @patch("queueradar.queue_times_collector.requests.get")
    def test_respects_limit(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_API_RESPONSE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        source = Source(
            name="Test Park",
            type="api",
            url="https://queue-times.com/parks/6/queue_times.json",
        )
        articles = collect_queue_times(source, category="queue", limit=2)
        assert len(articles) == 2

    @patch("queueradar.queue_times_collector.requests.get")
    def test_all_articles_have_queue_category(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_API_RESPONSE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        source = Source(
            name="Test Park",
            type="api",
            url="https://queue-times.com/parks/6/queue_times.json",
        )
        articles = collect_queue_times(source, category="queue")
        for article in articles:
            assert article.category == "queue"
            assert isinstance(article, Article)
