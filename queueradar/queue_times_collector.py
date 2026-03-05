from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, List

import requests

from .models import Article, Source


def collect_queue_times(
    source: Source,
    *,
    category: str,
    limit: int = 50,
    timeout: int = 15,
) -> List[Article]:
    """Fetch ride wait times from Queue-Times API for a specific park.

    Each ride in the park becomes one Article with structured wait-time data.
    API docs: https://queue-times.com/en-US/pages/api
    """
    response = requests.get(source.url, timeout=timeout)
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    park_name = source.name
    park_id = _extract_park_id(source.url)
    park_url = (
        f"https://queue-times.com/en-US/parks/{park_id}/queue_times"
        if park_id
        else source.url
    )

    articles: List[Article] = []

    lands: list[dict[str, Any]] = data.get("lands", [])
    for land in lands:
        land_name: str = land.get("name", "Unknown Area")
        rides: list[dict[str, Any]] = land.get("rides", [])
        for ride in rides:
            article = _ride_to_article(
                ride,
                park_name=park_name,
                land_name=land_name,
                park_url=park_url,
                category=category,
            )
            if article:
                articles.append(article)

    top_rides: list[dict[str, Any]] = data.get("rides", [])
    for ride in top_rides:
        article = _ride_to_article(
            ride,
            park_name=park_name,
            land_name="General",
            park_url=park_url,
            category=category,
        )
        if article:
            articles.append(article)

    return articles[:limit]


def _ride_to_article(
    ride: dict[str, Any],
    *,
    park_name: str,
    land_name: str,
    park_url: str,
    category: str,
) -> Article | None:
    """Convert a single ride wait-time entry into an Article."""
    name: str = ride.get("name", "")
    if not name:
        return None

    is_open: bool = ride.get("is_open", False)
    wait_time: int = ride.get("wait_time", 0)
    last_updated_str: str = ride.get("last_updated", "")

    status = "Open" if is_open else "Closed"
    if is_open and wait_time > 0:
        wait_display = f"{wait_time} minutes wait"
    elif is_open:
        wait_display = "No wait"
    else:
        wait_display = "Closed"

    title = f"{name} - {wait_display} ({park_name})"

    summary_parts = [
        f"Attraction: {name}.",
        f"Current wait time: {wait_time} minutes.",
        f"Status: {status}.",
        f"Location: {land_name}, {park_name}.",
        f"Last updated: {last_updated_str}.",
        "Real-time queue data powered by Queue-Times.com.",
    ]
    summary = " ".join(summary_parts)

    published = _parse_iso_datetime(last_updated_str)

    ride_id = ride.get("id", "")
    link = f"{park_url}#ride-{ride_id}" if ride_id else park_url

    return Article(
        title=title,
        link=link,
        summary=summary,
        published=published,
        source=park_name,
        category=category,
    )


def _parse_iso_datetime(dt_str: str) -> datetime | None:
    """Parse ISO 8601 datetime string to timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        cleaned = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_park_id(url: str) -> str | None:
    """Extract park ID from a Queue-Times URL like /parks/6/queue_times.json."""
    match = re.search(r"/parks/(\d+)/", url)
    return match.group(1) if match else None
