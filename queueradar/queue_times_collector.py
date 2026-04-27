from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import structlog

from .models import Article, Source


logger = structlog.get_logger(__name__)

_API_TIMEOUT = int(os.environ.get("QUEUE_TIMES_API_TIMEOUT", "15"))
_CACHE_DIR = Path(os.environ.get("QUEUE_TIMES_CACHE_DIR", "data/api_cache"))
_CACHE_TTL_SECONDS = int(os.environ.get("QUEUE_TIMES_CACHE_TTL", "300"))


def _cache_file_for(source_name: str) -> Path:
    """Get cache file path for a source."""
    safe_name = source_name.replace("/", "_").replace(" ", "_").lower()
    return _CACHE_DIR / f"queue_times_{safe_name}.json"


def _load_cached_response(cache_file: Path) -> dict[str, Any] | None:
    """Load cached API response if fresh."""
    if not cache_file.exists():
        return None

    try:
        meta_file = cache_file.with_suffix(".meta.json")
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            cached_at = meta.get("cached_at", 0)
            if time.time() - cached_at > _CACHE_TTL_SECONDS:
                logger.debug("queue_times_cache_expired", cache_file=str(cache_file))
                return None

        data = json.loads(cache_file.read_text())
        if isinstance(data, dict):
            return data
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("queue_times_cache_read_error", error=str(exc))
        return None


def _load_stale_cache(cache_file: Path) -> dict[str, Any] | None:
    """Load cached response regardless of TTL (for fallback on API failure)."""
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())
        if isinstance(data, dict):
            return data
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("queue_times_stale_cache_error", error=str(exc))
        return None


def _save_cache(cache_file: Path, data: dict[str, Any]) -> None:
    """Save API response to file cache."""
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data))

        meta_file = cache_file.with_suffix(".meta.json")
        meta_file.write_text(json.dumps({"cached_at": time.time()}))
    except OSError as exc:
        logger.warning("queue_times_cache_write_error", error=str(exc))


def collect_queue_times(
    source: Source,
    *,
    category: str,
    limit: int = 50,
    timeout: int | None = None,
    session: requests.Session | None = None,
) -> list[Article]:
    """Fetch ride wait times from Queue-Times API for a specific park.

    Each ride in the park becomes one Article with structured wait-time data.
    API docs: https://queue-times.com/en-US/pages/api

    Features:
    - File-based response caching with configurable TTL
    - Configurable timeout via env var or parameter
    - Graceful degradation: falls back to stale cache on API failure
    """
    effective_timeout = timeout if timeout is not None else _API_TIMEOUT
    client = session or requests
    cache_file = _cache_file_for(source.name)

    cached_data = _load_cached_response(cache_file)
    if cached_data is not None:
        logger.debug("using_cached_queue_times_response", source=source.name)
        return _parse_queue_data(cached_data, source=source, category=category, limit=limit)

    try:
        response = client.get(source.url, timeout=effective_timeout)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            logger.warning(
                "queue_times_rate_limited",
                source=source.name,
                retry_after=retry_after,
            )
            stale = _load_stale_cache(cache_file)
            if stale is not None:
                logger.info("using_stale_cache_after_rate_limit", source=source.name)
                return _parse_queue_data(stale, source=source, category=category, limit=limit)
            return []

        response.raise_for_status()

    except requests.exceptions.Timeout:
        logger.warning("queue_times_api_timeout", source=source.name, timeout=effective_timeout)
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)
    except requests.exceptions.ConnectionError as exc:
        logger.warning("queue_times_api_connection_error", source=source.name, error=str(exc))
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)
    except requests.exceptions.HTTPError as exc:
        logger.warning(
            "queue_times_api_http_error",
            source=source.name,
            status_code=getattr(exc.response, "status_code", None),
        )
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)
    except requests.exceptions.RequestException as exc:
        logger.warning("queue_times_api_request_error", source=source.name, error=str(exc))
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)

    try:
        data: dict[str, Any] = response.json()
    except ValueError as exc:
        logger.warning("queue_times_invalid_json", source=source.name, error=str(exc))
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)

    if not isinstance(data, dict):
        logger.warning(
            "queue_times_unexpected_response_type",
            source=source.name,
            response_type=type(data).__name__,
        )
        return _fallback_to_cache(cache_file, source=source, category=category, limit=limit)

    _save_cache(cache_file, data)

    return _parse_queue_data(data, source=source, category=category, limit=limit)


def _fallback_to_cache(
    cache_file: Path,
    *,
    source: Source,
    category: str,
    limit: int,
) -> list[Article]:
    """Attempt to return data from stale cache, or empty list."""
    stale = _load_stale_cache(cache_file)
    if stale is not None:
        logger.info(
            "using_stale_cache_fallback",
            source=source.name,
            cache_file=str(cache_file),
        )
        return _parse_queue_data(stale, source=source, category=category, limit=limit)

    logger.warning("queue_times_api_unavailable_no_cache", source=source.name)
    return []


def _parse_queue_data(
    data: dict[str, Any],
    *,
    source: Source,
    category: str,
    limit: int,
) -> list[Article]:
    """Parse Queue-Times API response data into Article objects."""
    park_name = source.name
    park_id = _extract_park_id(source.url)
    park_url = (
        f"https://queue-times.com/en-US/parks/{park_id}/queue_times" if park_id else source.url
    )

    articles: list[Article] = []

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
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_park_id(url: str) -> str | None:
    """Extract park ID from a Queue-Times URL like /parks/6/queue_times.json."""
    match = re.search(r"/parks/(\d+)/", url)
    return match.group(1) if match else None
