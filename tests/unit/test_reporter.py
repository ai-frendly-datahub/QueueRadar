from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from queueradar.models import Article, CategoryConfig, Source
from queueradar.reporter import generate_report


pytestmark = pytest.mark.unit


def test_report_includes_queue_quality_panel(tmp_path: Path) -> None:
    output_path = tmp_path / "queue_report.html"
    category = CategoryConfig(
        category_name="queue",
        display_name="Queue",
        sources=[
            Source(
                name="Disney Magic Kingdom",
                type="api",
                url="https://queue-times.com/parks/6/queue_times.json",
            )
        ],
        entities=[],
    )
    article = Article(
        title="Space Mountain - 75 minutes wait (Disney Magic Kingdom)",
        link="https://queue-times.com/en-US/parks/6/queue_times#ride-1234",
        summary="Attraction: Space Mountain. Current wait time: 75 minutes. Status: Open.",
        published=datetime(2026, 4, 14, tzinfo=UTC),
        source="Disney Magic Kingdom",
        category="queue",
    )
    quality_report = {
        "summary": {
            "queue_signal_event_count": 1,
            "wait_time_observation_count": 1,
            "open_attraction_count": 1,
            "closed_attraction_count": 0,
            "target_canonical_key_present_count": 1,
            "event_required_field_gap_count": 1,
            "daily_review_item_count": 1,
        },
        "events": [
            {
                "event_model": "wait_time_snapshot",
                "source": "Disney Magic Kingdom",
                "attraction_name": "Space Mountain",
                "wait_minutes": 75,
                "availability_status": "Open",
                "canonical_key": "queue_target:6:ride:1234",
            }
        ],
        "daily_review_items": [
            {
                "reason": "missing_required_fields",
                "source": "Park ticket pricing pages",
                "canonical_key": "queue_target:park-1",
            }
        ],
    }

    result = generate_report(
        category=category,
        articles=[article],
        output_path=output_path,
        stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
        quality_report=quality_report,
    )

    html = result.read_text(encoding="utf-8")
    assert "Queue Quality" in html
    assert "wait_time_snapshot" in html
    assert "Space Mountain" in html
    assert "queue_target:6:ride:1234" in html
    assert "missing_required_fields" in html

    dated_html = next(tmp_path.glob("queue_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].html"))
    dated_text = dated_html.read_text(encoding="utf-8")
    assert "Queue Quality" in dated_text
    assert "queue_target:6:ride:1234" in dated_text

    summaries = sorted(tmp_path.glob("queue_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_summary.json"))
    assert len(summaries) == 1
    summary = summaries[0].read_text(encoding="utf-8")
    assert '"repo": "QueueRadar"' in summary
    assert '"ontology_version": "0.1.0"' in summary
    assert '"queue.wait_time_snapshot"' in summary
