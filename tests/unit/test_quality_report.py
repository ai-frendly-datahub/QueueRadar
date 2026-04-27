from __future__ import annotations

from datetime import UTC, datetime

import pytest

from queueradar.models import Article, CategoryConfig, Source
from queueradar.quality_report import build_quality_report


pytestmark = pytest.mark.unit


def test_build_quality_report_extracts_queue_target_keys() -> None:
    source = Source(
        name="Disney Magic Kingdom",
        type="api",
        url="https://queue-times.com/parks/6/queue_times.json",
        trust_tier="T1_official",
        content_type="queue_times",
    )
    category = CategoryConfig(
        category_name="queue",
        display_name="Queue",
        sources=[source],
        entities=[],
    )
    article = Article(
        title="Space Mountain - 75 minutes wait (Disney Magic Kingdom)",
        link="https://queue-times.com/en-US/parks/6/queue_times#ride-1234",
        summary=(
            "Attraction: Space Mountain. Current wait time: 75 minutes. "
            "Status: Open. Location: Tomorrowland, Disney Magic Kingdom. "
            "Last updated: 2026-04-14T02:25:16.000Z."
        ),
        published=datetime(2026, 4, 14, 2, 25, 16, tzinfo=UTC),
        source="Disney Magic Kingdom",
        category="queue",
    )

    report = build_quality_report(
        category=category,
        articles=[article],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["wait_time_snapshot"]},
                "event_models": {
                    "wait_time_snapshot": {
                        "required_fields": [
                            "facility_id",
                            "attraction_id",
                            "wait_minutes",
                            "source_url",
                        ]
                    }
                },
            },
            "source_backlog": {
                "operational_candidates": [
                    {
                        "name": "Park reservation slot pages",
                        "signal_type": "reservation_slot",
                        "activation_gate": "ToS review",
                    }
                ]
            },
        },
        generated_at=datetime(2026, 4, 14, 3, tzinfo=UTC),
    )

    summary = report["summary"]
    assert summary["queue_signal_event_count"] == 1
    assert summary["wait_time_observation_count"] == 1
    assert summary["open_attraction_count"] == 1
    assert summary["high_wait_review_count"] == 1
    assert summary["target_canonical_key_present_count"] == 1
    assert summary["event_required_field_gap_count"] == 0
    assert summary["source_backlog_candidate_count"] == 1

    event = report["events"][0]
    assert event["facility_id"] == "6"
    assert event["facility_name"] == "Disney Magic Kingdom"
    assert event["attraction_id"] == "1234"
    assert event["attraction_name"] == "Space Mountain"
    assert event["wait_minutes"] == 75
    assert event["availability_status"] == "Open"
    assert event["canonical_key"] == "queue_target:6:ride:1234"
    assert event["canonical_key_status"] == "complete"
    assert event["required_field_gaps"] == []
    assert any(item["reason"] == "high_wait_review" for item in report["daily_review_items"])
    assert any(
        item["reason"] == "source_backlog_pending"
        for item in report["daily_review_items"]
    )


def test_build_quality_report_flags_ticket_price_required_gaps() -> None:
    source = Source(
        name="Park ticket pricing pages",
        type="rss",
        url="https://example.com/tickets",
        config={"event_model": "ticket_price", "facility_id": "park-1"},
    )
    category = CategoryConfig(
        category_name="queue",
        display_name="Queue",
        sources=[source],
        entities=[],
    )
    article = Article(
        title="New admission details",
        link="https://example.com/tickets/update",
        summary="Ticket type: One day pass. Currency: USD.",
        published=datetime(2026, 4, 14, tzinfo=UTC),
        source="Park ticket pricing pages",
        category="queue",
    )

    report = build_quality_report(
        category=category,
        articles=[article],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["ticket_price"]},
                "event_models": {
                    "ticket_price": {
                        "required_fields": [
                            "facility_id",
                            "ticket_type",
                            "price",
                            "currency",
                        ]
                    }
                },
            }
        },
        generated_at=datetime(2026, 4, 14, tzinfo=UTC),
    )

    event = report["events"][0]
    assert event["canonical_key"] == "queue_target:park-1"
    assert event["canonical_key_status"] == "facility_proxy"
    assert event["ticket_type"] == "One day pass"
    assert "price" in event["required_field_gaps"]
    assert report["summary"]["event_required_field_gap_count"] == 1
    assert any(
        item["reason"] == "missing_required_fields"
        for item in report["daily_review_items"]
    )


def test_build_quality_report_excludes_disabled_sources_from_active_tracking() -> None:
    enabled_source = Source(
        name="Enabled Park",
        type="api",
        url="https://queue-times.com/parks/6/queue_times.json",
        content_type="queue_times",
    )
    disabled_source = Source(
        name="Disabled Park",
        type="api",
        url="https://queue-times.com/parks/7/queue_times.json",
        enabled=False,
        content_type="queue_times",
        config={
            "disabled_reason": "api_contract_changed",
            "required_before_enable": ["parser_smoke"],
        },
    )
    category = CategoryConfig(
        category_name="queue",
        display_name="Queue",
        sources=[enabled_source, disabled_source],
        entities=[],
    )
    generated_at = datetime(2026, 4, 14, 3, tzinfo=UTC)
    articles = [
        Article(
            title="Space Mountain - 30 minutes wait (Enabled Park)",
            link="https://queue-times.com/en-US/parks/6/queue_times#ride-1234",
            summary="Attraction: Space Mountain. Current wait time: 30 minutes. Status: Open.",
            published=generated_at,
            source="Enabled Park",
            category="queue",
        ),
        Article(
            title="Tower - 40 minutes wait (Disabled Park)",
            link="https://queue-times.com/en-US/parks/7/queue_times#ride-7777",
            summary="Attraction: Tower. Current wait time: 40 minutes. Status: Open.",
            published=generated_at,
            source="Disabled Park",
            category="queue",
        ),
    ]

    report = build_quality_report(
        category=category,
        articles=articles,
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["wait_time_snapshot"]},
            }
        },
        generated_at=generated_at,
    )

    assert report["summary"]["tracked_sources"] == 1
    assert report["summary"]["fresh_sources"] == 1
    assert report["summary"]["skipped_disabled_sources"] == 1
    assert report["summary"]["wait_time_snapshot_events"] == 1

    disabled_row = next(row for row in report["sources"] if row["source"] == "Disabled Park")
    assert disabled_row["enabled"] is False
    assert disabled_row["tracked"] is False
    assert disabled_row["status"] == "skipped_disabled"
    assert disabled_row["disabled_reason"] == "api_contract_changed"
    assert disabled_row["required_before_enable"] == ["parser_smoke"]
    assert all(row["source"] != "Disabled Park" for row in report["events"])
