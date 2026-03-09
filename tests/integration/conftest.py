from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from queueradar.models import Article, CategoryConfig, EntityDefinition, Source
from queueradar.storage import RadarStorage


@pytest.fixture
def tmp_storage(tmp_path: Path) -> RadarStorage:
    """Create a temporary RadarStorage instance for testing."""
    db_path = tmp_path / "test.duckdb"
    storage = RadarStorage(db_path)
    yield storage
    storage.close()


@pytest.fixture
def sample_articles() -> list[Article]:
    """Create sample articles with realistic queue time data."""
    now = datetime.now(timezone.utc)
    return [
        Article(
            title="병원 응급실 대기시간 현황",
            link="https://queue.example.com/hospital-er-2024",
            summary="서울 주요 병원 응급실 대기시간이 30분 이상입니다. 혼잡도 높음.",
            published=now,
            source="queue_api",
            category="queue",
            matched_entities={},
        ),
        Article(
            title="테마파크 놀이기구 대기시간",
            link="https://queue.example.com/theme-park-2024",
            summary="롯데월드 주요 놀이기구 대기시간이 60분 이상입니다.",
            published=now,
            source="queue_api",
            category="queue",
            matched_entities={},
        ),
        Article(
            title="관공서 민원 대기시간 안내",
            link="https://queue.example.com/government-2024",
            summary="서울시청 민원실 대기시간이 20분입니다. 혼잡도 보통.",
            published=now,
            source="queue_api",
            category="queue",
            matched_entities={},
        ),
        Article(
            title="은행 창구 대기시간 현황",
            link="https://queue.example.com/bank-2024",
            summary="국민은행 강남지점 창구 대기시간이 15분입니다.",
            published=now,
            source="queue_api",
            category="queue",
            matched_entities={},
        ),
        Article(
            title="음식점 대기시간 정보",
            link="https://queue.example.com/restaurant-2024",
            summary="인기 음식점들의 대기시간이 30분 이상입니다.",
            published=now,
            source="queue_api",
            category="queue",
            matched_entities={},
        ),
    ]


@pytest.fixture
def sample_entities() -> list[EntityDefinition]:
    """Create sample entities with queue-related keywords."""
    return [
        EntityDefinition(
            name="healthcare",
            display_name="의료시설",
            keywords=["병원", "응급실", "진료", "의료", "대기"],
        ),
        EntityDefinition(
            name="theme_park",
            display_name="테마파크",
            keywords=["테마파크", "놀이공원", "놀이기구", "줄서기", "대기"],
        ),
        EntityDefinition(
            name="government",
            display_name="관공서",
            keywords=["관공서", "민원", "시청", "구청", "대기"],
        ),
        EntityDefinition(
            name="banking",
            display_name="금융기관",
            keywords=["은행", "창구", "금융", "대기", "시간"],
        ),
        EntityDefinition(
            name="food_service",
            display_name="음식점",
            keywords=["음식점", "식당", "카페", "대기", "줄"],
        ),
    ]


@pytest.fixture
def sample_config(tmp_path: Path, sample_entities: list[EntityDefinition]) -> CategoryConfig:
    """Create a sample CategoryConfig for testing."""
    sources = [
        Source(
            name="queue_api",
            type="api",
            url="https://api.queue.example.com/times",
        ),
    ]
    return CategoryConfig(
        category_name="queue",
        display_name="대기시간",
        sources=sources,
        entities=sample_entities,
    )
