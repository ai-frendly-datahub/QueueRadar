from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import CategoryConfig, Source


DEFAULT_EVENT_MODELS = [
    "wait_time_snapshot",
    "reservation_slot",
    "ticket_price",
    "weather_context",
]
SUMMARY_LABELS = [
    "Attraction",
    "Current wait time",
    "Wait time",
    "Status",
    "Location",
    "Facility",
    "Park",
    "Service",
    "Slot time",
    "Availability",
    "Availability status",
    "Ticket type",
    "Price",
    "Currency",
    "Weather metric",
    "Metric value",
    "Last updated",
]


def build_quality_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Any],
    errors: Iterable[str] | None = None,
    quality_config: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = _as_utc(generated_at or datetime.now(UTC))
    article_rows = list(articles)
    error_rows = [str(error) for error in (errors or [])]
    quality = _dict(quality_config or {}, "data_quality")
    event_model_config = _dict(quality, "event_models")
    tracked_models = _tracked_event_models(quality)

    events = _build_events(
        articles=article_rows,
        sources=category.sources,
        tracked_models=tracked_models,
        event_model_config=event_model_config,
    )
    source_rows = [
        _build_source_row(
            source=source,
            articles=article_rows,
            events=events,
            errors=error_rows,
            quality=quality,
            tracked_models=tracked_models,
            generated_at=generated,
        )
        for source in category.sources
    ]

    status_counts = Counter(str(row["status"]) for row in source_rows)
    event_counts = Counter(str(row["event_model"]) for row in events)
    summary: dict[str, Any] = {
        "total_sources": len(source_rows),
        "enabled_sources": sum(1 for row in source_rows if row["enabled"]),
        "tracked_sources": sum(1 for row in source_rows if row["tracked"]),
        "fresh_sources": status_counts.get("fresh", 0),
        "stale_sources": status_counts.get("stale", 0),
        "missing_sources": status_counts.get("missing", 0),
        "missing_event_sources": status_counts.get("missing_event", 0),
        "unknown_event_date_sources": status_counts.get("unknown_event_date", 0),
        "not_tracked_sources": status_counts.get("not_tracked", 0),
        "skipped_disabled_sources": status_counts.get("skipped_disabled", 0),
        "collection_error_count": len(error_rows),
    }
    for event_model in tracked_models:
        summary[f"{event_model}_events"] = event_counts.get(event_model, 0)
    summary.update(_event_quality_summary(events, source_rows, quality_config or {}, tracked_models))
    daily_review_items = _daily_review_items(events, source_rows, quality_config or {}, tracked_models)
    summary["daily_review_item_count"] = len(daily_review_items)

    return {
        "category": category.category_name,
        "generated_at": generated.isoformat(),
        "scope_note": (
            f"{category.display_name} quality report is generated from repo-local "
            "category data_quality metadata and recent stored articles. Operational "
            "backlog sources remain separate until dedicated source-level fields are collected."
        ),
        "summary": summary,
        "sources": source_rows,
        "events": events,
        "daily_review_items": daily_review_items,
        "source_backlog": (quality_config or {}).get("source_backlog", {}),
        "errors": error_rows,
    }


def write_quality_report(
    report: Mapping[str, object],
    *,
    output_dir: Path,
    category_name: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _parse_datetime(str(report.get("generated_at") or "")) or datetime.now(UTC)
    date_stamp = _as_utc(generated_at).strftime("%Y%m%d")
    latest_path = output_dir / f"{category_name}_quality.json"
    dated_path = output_dir / f"{category_name}_{date_stamp}_quality.json"
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    latest_path.write_text(encoded + "\n", encoding="utf-8")
    dated_path.write_text(encoded + "\n", encoding="utf-8")
    return {"latest": latest_path, "dated": dated_path}


def _build_events(
    *,
    articles: list[Any],
    sources: list[Source],
    tracked_models: list[str],
    event_model_config: Mapping[str, object],
) -> list[dict[str, Any]]:
    source_map = {source.name: source for source in sources}
    rows: list[dict[str, Any]] = []
    for article in articles:
        source = source_map.get(_article_source(article))
        if source is None:
            continue
        if not source.enabled:
            continue
        event_model = _source_event_model(source, tracked_models)
        if event_model not in tracked_models:
            continue
        event_at = _event_datetime(article)
        rows.append(_event_row(article, source, event_model, event_at, event_model_config))
    return rows


def _event_row(
    article: Any,
    source: Source,
    event_model: str,
    event_at: datetime | None,
    event_model_config: Mapping[str, object],
) -> dict[str, Any]:
    wait_minutes = _wait_minutes(article)
    price = _price(article)
    metric_value = _metric_value(article)
    row: dict[str, Any] = {
        "source": source.name,
        "source_type": source.type,
        "trust_tier": source.trust_tier,
        "content_type": source.content_type,
        "collection_tier": source.collection_tier,
        "producer_role": source.producer_role,
        "event_model": event_model,
        "title": _article_title(article),
        "url": _article_link(article),
        "source_url": _article_link(article) or source.url,
        "event_at": event_at.isoformat() if event_at else None,
        "matched_entities": _article_entities(article),
        "facility_id": _facility_id(article, source),
        "facility_name": _facility_name(article, source),
        "attraction_id": _attraction_id(article),
        "attraction_name": _attraction_name(article),
        "service_id": _service_id(article),
        "timezone": str(source.config.get("timezone") or source.config.get("tz") or ""),
        "wait_minutes": wait_minutes,
        "availability_status": _availability_status(article),
        "ticket_type": _ticket_type(article),
        "price": price,
        "currency": _currency(article),
        "weather_metric": _weather_metric(article),
        "metric_value": metric_value,
    }
    canonical_key, canonical_key_status = _canonical_key(row)
    row["canonical_key"] = canonical_key
    row["canonical_key_status"] = canonical_key_status
    row["event_key"] = _event_key(row, event_model, event_at)
    row["queue_target_key"] = _queue_target_key(row)
    row["required_field_proxy"] = _required_field_proxy(
        article=article,
        source=source,
        event_model=event_model,
        event_model_config=event_model_config,
    )
    row["required_field_gaps"] = _required_field_gaps(row, event_model, event_model_config)
    return row


def _build_source_row(
    *,
    source: Source,
    articles: list[Any],
    events: list[dict[str, Any]],
    errors: list[str],
    quality: Mapping[str, object],
    tracked_models: list[str],
    generated_at: datetime,
) -> dict[str, Any]:
    source_articles = [article for article in articles if _article_source(article) == source.name]
    event_model = _source_event_model(source, tracked_models)
    source_events = [
        row
        for row in events
        if row["source"] == source.name and row["event_model"] == event_model
    ]
    latest_event = _latest_event(source_events)
    latest_event_at = (
        _parse_datetime(str(latest_event.get("event_at") or "")) if latest_event else None
    )
    sla_days = _source_sla_days(source, event_model, _dict(quality, "freshness_sla"))
    age_days = _age_days(generated_at, latest_event_at) if latest_event_at else None
    source_errors = [error for error in errors if error.startswith(f"{source.name}:")]

    tracked = _is_tracked_source(source, event_model, tracked_models)
    status = _source_status(
        source=source,
        tracked=tracked,
        article_count=len(source_articles),
        event_count=len(source_events),
        latest_event_at=latest_event_at,
        sla_days=sla_days,
        age_days=age_days,
    )

    return {
        "source": source.name,
        "source_type": source.type,
        "enabled": source.enabled,
        "trust_tier": source.trust_tier,
        "content_type": source.content_type,
        "collection_tier": source.collection_tier,
        "producer_role": source.producer_role,
        "info_purpose": source.info_purpose,
        "tracked": tracked,
        "disabled_reason": _source_disabled_reason(source),
        "required_before_enable": _source_required_before_enable(source),
        "event_model": event_model,
        "freshness_sla_days": sla_days,
        "status": status,
        "article_count": len(source_articles),
        "event_count": len(source_events),
        "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "latest_title": str(latest_event.get("title", "")) if latest_event else "",
        "latest_url": str(latest_event.get("url", "")) if latest_event else "",
        "latest_required_field_proxy": (
            latest_event.get("required_field_proxy", {}) if latest_event else {}
        ),
        "latest_canonical_key": str(latest_event.get("canonical_key", "")) if latest_event else "",
        "latest_required_field_gaps": (
            latest_event.get("required_field_gaps", []) if latest_event else []
        ),
        "errors": source_errors,
    }


def _tracked_event_models(quality: Mapping[str, object]) -> list[str]:
    outputs = _dict(quality, "quality_outputs")
    raw = outputs.get("tracked_event_models")
    if isinstance(raw, list):
        values = [str(value).strip() for value in raw if str(value).strip()]
        if values:
            return values
    event_models = _dict(quality, "event_models")
    if event_models:
        return list(event_models.keys())
    return DEFAULT_EVENT_MODELS


def _source_event_model(source: Source, tracked_models: list[str]) -> str:
    raw = source.config.get("event_model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    for value in source.info_purpose:
        if value in tracked_models:
            return value

    text = " ".join(
        [
            source.name,
            source.type,
            source.content_type,
            source.collection_tier,
            source.producer_role,
            " ".join(source.info_purpose),
            " ".join(str(value) for value in source.config.values()),
        ]
    ).lower()
    type_value = source.type.lower()

    model_rules = [
        ("queue-times", "wait_time_snapshot"),
        ("wait time", "wait_time_snapshot"),
        ("queue", "wait_time_snapshot"),
        ("standby", "wait_time_snapshot"),
        ("reservation", "reservation_slot"),
        ("slot", "reservation_slot"),
        ("availability", "reservation_slot"),
        ("ticket", "ticket_price"),
        ("price", "ticket_price"),
        ("admission", "ticket_price"),
        ("weather", "weather_context"),
        ("forecast", "weather_context"),
        ("benchmark", "benchmark_result"),
        ("leaderboard", "benchmark_result"),
        ("citation", "citation_snapshot"),
        ("repository", "code_repository"),
        ("github", "code_repository"),
        ("code", "code_repository"),
        ("preprint", "paper_release"),
        ("academic", "paper_release"),
        ("research", "paper_release"),
        ("transaction", "transaction_record"),
        ("presale", "presale_competition"),
        ("competition", "presale_competition"),
        ("listing", "listing_inventory"),
        ("inventory", "listing_inventory"),
        ("permit", "permit_completion"),
        ("completion", "permit_completion"),
    ]
    if type_value == "api" and "wait_time_snapshot" in tracked_models:
        return "wait_time_snapshot"
    for token, event_model in model_rules:
        if token in text and event_model in tracked_models:
            return event_model
    return ""


def _is_tracked_source(source: Source, event_model: str, tracked_models: list[str]) -> bool:
    return source.enabled and event_model in tracked_models


def _source_disabled_reason(source: Source) -> str:
    raw = source.config.get("disabled_reason")
    return str(raw).strip() if raw is not None else ""


def _source_required_before_enable(source: Source) -> list[str]:
    raw = source.config.get("required_before_enable")
    if not isinstance(raw, list):
        return []
    return [str(value).strip() for value in raw if str(value).strip()]


def _event_quality_summary(
    events: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    quality_config: Mapping[str, object],
    tracked_models: list[str],
) -> dict[str, int]:
    event_counts = Counter(str(row.get("event_model") or "") for row in events)
    return {
        "queue_signal_event_count": sum(event_counts.get(model, 0) for model in tracked_models),
        "wait_time_observation_count": sum(
            1 for row in events if row.get("event_model") == "wait_time_snapshot"
        ),
        "open_attraction_count": sum(
            1 for row in events if str(row.get("availability_status") or "").lower() == "open"
        ),
        "closed_attraction_count": sum(
            1 for row in events if str(row.get("availability_status") or "").lower() == "closed"
        ),
        "zero_wait_count": sum(1 for row in events if row.get("wait_minutes") == 0),
        "high_wait_review_count": sum(
            1
            for row in events
            if isinstance(row.get("wait_minutes"), int) and int(row["wait_minutes"]) >= 60
        ),
        "target_canonical_key_present_count": sum(
            1 for row in events if str(row.get("canonical_key") or "").startswith("queue_target:")
        ),
        "attraction_canonical_key_present_count": sum(
            1 for row in events if row.get("attraction_id") and row.get("attraction_name")
        ),
        "reservation_canonical_key_present_count": sum(
            1
            for row in events
            if row.get("event_model") == "reservation_slot" and row.get("canonical_key")
        ),
        "ticket_canonical_key_present_count": sum(
            1 for row in events if row.get("event_model") == "ticket_price" and row.get("canonical_key")
        ),
        "weather_context_present_count": sum(
            1 for row in events if row.get("event_model") == "weather_context" and row.get("metric_value") is not None
        ),
        "missing_canonical_key_count": sum(1 for row in events if not row.get("canonical_key")),
        "event_required_field_gap_count": sum(
            len(row.get("required_field_gaps") or []) for row in events
        ),
        "tracked_source_gap_count": sum(
            1
            for row in source_rows
            if row.get("tracked")
            and row.get("status") in {"missing", "missing_event", "unknown_event_date", "stale"}
        ),
        "missing_event_model_count": sum(
            1 for model in tracked_models if event_counts.get(model, 0) == 0
        ),
        "source_backlog_candidate_count": len(_source_backlog_items(quality_config)),
    }


def _daily_review_items(
    events: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    quality_config: Mapping[str, object],
    tracked_models: list[str],
) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for row in events:
        gaps = [str(value) for value in row.get("required_field_gaps") or []]
        if gaps:
            review.append(
                {
                    "reason": "missing_required_fields",
                    "event_model": row.get("event_model"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "canonical_key": row.get("canonical_key"),
                    "required_field_gaps": gaps,
                }
            )
        if not row.get("canonical_key"):
            review.append(
                {
                    "reason": "missing_canonical_key",
                    "event_model": row.get("event_model"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "event_key": row.get("event_key"),
                }
            )
        if isinstance(row.get("wait_minutes"), int) and int(row["wait_minutes"]) >= 60:
            review.append(
                {
                    "reason": "high_wait_review",
                    "event_model": row.get("event_model"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "canonical_key": row.get("canonical_key"),
                    "wait_minutes": row.get("wait_minutes"),
                }
            )

    for source in source_rows:
        if not source.get("tracked"):
            continue
        if source.get("status") in {"missing", "missing_event", "unknown_event_date", "stale"}:
            review.append(
                {
                    "reason": f"source_{source.get('status')}",
                    "source": source.get("source"),
                    "event_model": source.get("event_model"),
                    "age_days": source.get("age_days"),
                    "latest_title": source.get("latest_title"),
                }
            )

    counts = Counter(str(row.get("event_model") or "") for row in events)
    for model in tracked_models:
        if counts.get(model, 0) == 0:
            review.append({"reason": "missing_event_model", "event_model": model})

    for item in _source_backlog_items(quality_config):
        review.append(
            {
                "reason": "source_backlog_pending",
                "source": item.get("name") or item.get("id"),
                "signal_type": item.get("signal_type"),
                "activation_gate": item.get("activation_gate"),
            }
        )
    return review[:50]


def _source_backlog_items(quality_config: Mapping[str, object]) -> list[Mapping[str, object]]:
    backlog = _dict(quality_config, "source_backlog")
    candidates = backlog.get("operational_candidates")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, Mapping)]


def _required_field_gaps(
    row: Mapping[str, Any],
    event_model: str,
    event_model_config: Mapping[str, object],
) -> list[str]:
    event_config = _dict(event_model_config, event_model)
    raw_fields = event_config.get("required_fields")
    if not isinstance(raw_fields, list):
        return []
    return [
        str(field)
        for field in raw_fields
        if str(field).strip() and not _field_present(row, str(field))
    ]


def _field_present(row: Mapping[str, Any], field: str) -> bool:
    normalized = field.lower()
    aliases = {
        "facility_id": ("facility_id", "facility_name"),
        "attraction_id": ("attraction_id", "attraction_name"),
        "service_id": ("service_id", "attraction_id", "facility_id"),
        "wait_minutes": ("wait_minutes",),
        "availability_status": ("availability_status",),
        "ticket_type": ("ticket_type",),
        "price": ("price",),
        "currency": ("currency",),
        "weather_metric": ("weather_metric",),
        "metric_value": ("metric_value", "wait_minutes", "price"),
        "source_url": ("source_url", "url"),
    }
    for alias in aliases.get(normalized, (normalized,)):
        value = row.get(alias)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _canonical_key(row: Mapping[str, Any]) -> tuple[str, str]:
    event_model = str(row.get("event_model") or "")
    facility = _slug(str(row.get("facility_id") or row.get("facility_name") or ""))
    attraction_id = _slug(str(row.get("attraction_id") or ""))
    attraction = _slug(str(row.get("attraction_name") or ""))
    service = _slug(str(row.get("service_id") or ""))
    if event_model in {"ticket_price", "weather_context"}:
        if facility and service:
            return f"queue_target:{facility}:service:{service}", "service_proxy"
        if facility:
            return f"queue_target:{facility}", "facility_proxy"
    if facility and attraction_id:
        return f"queue_target:{facility}:ride:{attraction_id}", "complete"
    if facility and attraction:
        return f"queue_target:{facility}:ride:{attraction}", "name_proxy"
    if facility and service:
        return f"queue_target:{facility}:service:{service}", "service_proxy"
    if facility:
        return f"queue_target:{facility}", "facility_proxy"
    return "", "missing"


def _queue_target_key(row: Mapping[str, Any]) -> str:
    canonical = str(row.get("canonical_key") or "")
    if canonical:
        return canonical
    basis = str(row.get("source_url") or row.get("title") or "")
    return f"queue_target:unknown:{_digest(basis)}" if basis else ""


def _event_key(row: Mapping[str, Any], event_model: str, event_at: datetime | None) -> str:
    observed = _as_utc(event_at).strftime("%Y%m%dT%H%M%SZ") if event_at else "undated"
    basis = _queue_target_key(row) or str(row.get("source_url") or row.get("title") or "")
    return f"{event_model}:{_digest(basis)}:{observed}"


def _facility_id(article: Any, source: Source) -> str:
    configured = _first_non_empty(source.config.get("facility_id"), source.config.get("park_id"))
    if configured:
        return _slug(configured)
    match = re.search(r"/parks/(\d+)/", f"{source.url} {_article_link(article)}")
    if match:
        return match.group(1)
    return _slug(source.name)


def _facility_name(article: Any, source: Source) -> str:
    labeled = _summary_value(article, "Facility", "Park", "Location")
    if labeled:
        parts = [part.strip() for part in labeled.split(",") if part.strip()]
        return parts[-1] if parts else labeled
    return source.name


def _attraction_id(article: Any) -> str:
    match = re.search(r"(?:#ride-|/rides/)([A-Za-z0-9_.-]+)", _article_link(article))
    return match.group(1) if match else ""


def _attraction_name(article: Any) -> str:
    labeled = _summary_value(article, "Attraction")
    if labeled:
        return labeled
    title = _article_title(article)
    if " - " in title:
        return title.split(" - ", 1)[0].strip()
    return title.strip()


def _service_id(article: Any) -> str:
    labeled = _summary_value(article, "Service")
    return _slug(labeled) if labeled else ""


def _wait_minutes(article: Any) -> int | None:
    value = getattr(article, "wait_minutes", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = f"{_article_title(article)} {_article_summary(article)}"
    for pattern in (
        r"(?:current\s+)?wait\s+time\s*[:=]\s*(\d+)\s*minutes?",
        r"(\d+)\s*minutes?\s+wait",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    if re.search(r"\bno\s+wait\b", text, flags=re.IGNORECASE):
        return 0
    return None


def _availability_status(article: Any) -> str:
    labeled = _summary_value(article, "Status", "Availability", "Availability status")
    if labeled:
        return labeled.split()[0].strip(" .;,")
    text = f"{_article_title(article)} {_article_summary(article)}"
    if re.search(r"\bclosed\b", text, flags=re.IGNORECASE):
        return "Closed"
    if re.search(r"\bopen\b", text, flags=re.IGNORECASE):
        return "Open"
    return ""


def _ticket_type(article: Any) -> str:
    return _summary_value(article, "Ticket type")


def _price(article: Any) -> float | None:
    value = getattr(article, "price", None)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    labeled = _summary_value(article, "Price")
    match = re.search(r"(\d+(?:\.\d+)?)", labeled)
    return float(match.group(1)) if match else None


def _currency(article: Any) -> str:
    explicit = _summary_value(article, "Currency").upper()
    if explicit:
        return explicit
    text = f"{_article_title(article)} {_article_summary(article)}"
    if "$" in text or re.search(r"\bUSD\b", text, flags=re.IGNORECASE):
        return "USD"
    if re.search(r"\bKRW\b|원", text, flags=re.IGNORECASE):
        return "KRW"
    return ""


def _weather_metric(article: Any) -> str:
    return _summary_value(article, "Weather metric")


def _metric_value(article: Any) -> str | None:
    return _summary_value(article, "Metric value") or None


def _summary_value(article: Any, *labels: str) -> str:
    text = " ".join(f"{_article_title(article)} {_article_summary(article)}".split())
    for label in labels:
        match = re.search(rf"\b{re.escape(label)}\s*[:=]\s*", text, flags=re.IGNORECASE)
        if not match:
            continue
        start = match.end()
        end = len(text)
        for next_label in SUMMARY_LABELS:
            next_match = re.search(
                rf"\b{re.escape(next_label)}\s*[:=]\s*",
                text[start:],
                flags=re.IGNORECASE,
            )
            if next_match:
                end = min(end, start + next_match.start())
        return text[start:end].strip(" \t\r\n.;,")
    return ""


def _first_non_empty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _slug(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9가-힣._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:120]


def _digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _source_sla_days(
    source: Source,
    event_model: str,
    freshness_sla: Mapping[str, object],
) -> float | None:
    raw_source_sla = source.config.get("freshness_sla_days")
    parsed_source_sla = _as_float(raw_source_sla)
    if parsed_source_sla is not None:
        return parsed_source_sla

    for key in (f"{event_model}_days", f"{event_model}_day"):
        parsed_days = _as_float(freshness_sla.get(key))
        if parsed_days is not None:
            return parsed_days
    for key in (f"{event_model}_hours", f"{event_model}_hour"):
        parsed_hours = _as_float(freshness_sla.get(key))
        if parsed_hours is not None:
            return parsed_hours / 24.0
    return None


def _source_status(
    *,
    source: Source,
    tracked: bool,
    article_count: int,
    event_count: int,
    latest_event_at: datetime | None,
    sla_days: float | None,
    age_days: float | None,
) -> str:
    if not source.enabled:
        return "skipped_disabled"
    if not tracked:
        return "not_tracked"
    if article_count == 0:
        return "missing"
    if event_count == 0:
        return "missing_event"
    if latest_event_at is None or age_days is None:
        return "unknown_event_date"
    if sla_days is not None and age_days > sla_days:
        return "stale"
    return "fresh"


def _required_field_proxy(
    *,
    article: Any,
    source: Source,
    event_model: str,
    event_model_config: Mapping[str, object],
) -> dict[str, bool]:
    event_config = _dict(event_model_config, event_model)
    raw_fields = event_config.get("required_fields")
    if not isinstance(raw_fields, list):
        return {}
    return {
        str(field): _has_required_field(article, source, str(field))
        for field in raw_fields
        if str(field).strip()
    }


def _has_required_field(article: Any, source: Source, field: str) -> bool:
    normalized = field.lower()
    title = _article_title(article)
    link = _article_link(article)
    summary = _article_summary(article)
    text = f"{title} {summary} {link}".lower()
    entities = _article_entities(article)
    entity_values = " ".join(
        str(value).lower()
        for values in entities.values()
        for value in (values if isinstance(values, list) else [values])
    )

    if normalized in {"source", "source_name"}:
        return bool(source.name)
    if normalized in {"source_url", "evidence_url"}:
        return bool(link or source.url)
    if normalized in {"title", "normalized_title"}:
        return bool(title)
    if normalized == "facility_id":
        return bool(_facility_id(article, source))
    if normalized == "attraction_id":
        return bool(_attraction_id(article) or _attraction_name(article))
    if normalized == "service_id":
        return bool(_service_id(article) or _attraction_id(article) or _facility_id(article, source))
    if normalized in {"paper_id", "project_id"}:
        return bool(link or title)
    if normalized in {"repository", "host", "owner", "repo"}:
        return "github.com/" in text
    if normalized == "wait_minutes":
        return _wait_minutes(article) is not None
    if normalized in {"availability_status", "status"}:
        return bool(_availability_status(article))
    if normalized == "ticket_type":
        return bool(_ticket_type(article))
    if normalized in {"price", "transaction_price"}:
        return _price(article) is not None
    if normalized in {"currency"}:
        return bool(_currency(article))
    if normalized == "weather_metric":
        return bool(_weather_metric(article))
    if normalized == "metric_value":
        return _metric_value(article) is not None
    if normalized in {"region_code", "complex_name", "property_type"}:
        return bool(entity_values or title)
    if normalized.endswith("_date") or normalized.endswith("_time") or normalized == "observed_at":
        return _event_datetime(article) is not None
    return normalized in text or normalized in entity_values


def _latest_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated: list[tuple[datetime, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for row in events:
        parsed = _parse_datetime(str(row.get("event_at") or ""))
        if parsed is None:
            undated.append(row)
        else:
            dated.append((parsed, row))
    if dated:
        return max(dated, key=lambda row: row[0])[1]
    return undated[0] if undated else None


def _event_datetime(article: Any) -> datetime | None:
    published = getattr(article, "published", None)
    collected = getattr(article, "collected_at", None)
    value = published if isinstance(published, datetime) else collected
    return _as_utc(value) if isinstance(value, datetime) else None


def _article_source(article: Any) -> str:
    return str(getattr(article, "source", "") or "")


def _article_title(article: Any) -> str:
    return str(getattr(article, "title", "") or "")


def _article_link(article: Any) -> str:
    return str(getattr(article, "link", "") or "")


def _article_summary(article: Any) -> str:
    return str(getattr(article, "summary", "") or getattr(article, "abstract", "") or "")


def _article_entities(article: Any) -> dict[str, Any]:
    raw = getattr(article, "matched_entities", {})
    return raw if isinstance(raw, dict) else {}


def _dict(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    raw = value.get(key)
    if isinstance(raw, Mapping):
        return {str(k): v for k, v in raw.items()}
    return {}


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _age_days(generated_at: datetime, event_at: datetime) -> float:
    return max(0.0, (_as_utc(generated_at) - _as_utc(event_at)).total_seconds() / 86400)
