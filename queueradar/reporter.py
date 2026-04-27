from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

from radar_core.ontology import build_summary_ontology_metadata
from radar_core.report_utils import (
    generate_index_html as _core_generate_index_html,
)
from radar_core.report_utils import (
    generate_report as _core_generate_report,
)

from .models import Article, CategoryConfig


def generate_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Article],
    output_path: Path,
    stats: dict[str, int],
    errors: list[str] | None = None,
    store=None,
    quality_report: Mapping[str, Any] | None = None,
) -> Path:
    """Generate HTML report (delegates to radar-core)."""
    articles_list = list(articles)
    plugin_charts = []

    # --- Universal plugins (entity heatmap + source reliability) ---
    try:
        from radar_core.plugins.entity_heatmap import get_chart_config as _heatmap_config

        _heatmap = _heatmap_config(articles=articles_list)
        if _heatmap is not None:
            plugin_charts.append(_heatmap)
    except Exception:
        pass
    try:
        from radar_core.plugins.source_reliability import get_chart_config as _reliability_config

        _reliability = _reliability_config(store=store)
        if _reliability is not None:
            plugin_charts.append(_reliability)
    except Exception:
        pass

    report_path = _core_generate_report(
        category=category,
        articles=articles_list,
        output_path=output_path,
        stats=stats,
        errors=errors,
        plugin_charts=plugin_charts if plugin_charts else None,
        ontology_metadata=build_summary_ontology_metadata(
            "QueueRadar",
            category_name=category.category_name,
            search_from=Path(__file__).resolve(),
        ),
    )
    if quality_report:
        for path in _quality_panel_report_paths(report_path, category.category_name):
            _inject_queue_quality_panel(path, quality_report)
    return report_path


def generate_index_html(
    report_dir: Path,
    summaries_dir: Path | None = None,
) -> Path:
    """Generate index.html (delegates to radar-core)."""
    radar_name = "Queue Radar"
    return _core_generate_index_html(report_dir, radar_name)


def _quality_panel_report_paths(report_path: Path, category_name: str) -> list[Path]:
    paths = [report_path]
    match = re.match(rf"{re.escape(category_name)}_report$", report_path.stem)
    if match:
        dated = sorted(report_path.parent.glob(f"{category_name}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].html"))
        if dated:
            paths.append(dated[-1])
    unique: list[Path] = []
    for path in paths:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def _inject_queue_quality_panel(report_path: Path, quality_report: Mapping[str, Any]) -> None:
    if not report_path.exists():
        return
    html = report_path.read_text(encoding="utf-8")
    marker = '<section id="queue-quality"'
    panel = _render_queue_quality_panel(quality_report)
    if marker in html:
        html = re.sub(
            r'\n<section id="queue-quality".*?</section>\n',
            f"\n{panel}\n",
            html,
            count=1,
            flags=re.DOTALL,
        )
    elif "</body>" in html:
        html = html.replace("</body>", f"{panel}\n</body>", 1)
    else:
        html = f"{html}\n{panel}\n"
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    report_path.write_text(html, encoding="utf-8")


def _render_queue_quality_panel(quality_report: Mapping[str, Any]) -> str:
    summary = _mapping(quality_report.get("summary"))
    chips = [
        ("Events", summary.get("queue_signal_event_count", 0)),
        ("Waits", summary.get("wait_time_observation_count", 0)),
        ("Open", summary.get("open_attraction_count", 0)),
        ("Closed", summary.get("closed_attraction_count", 0)),
        ("Targets", summary.get("target_canonical_key_present_count", 0)),
        ("Field gaps", summary.get("event_required_field_gap_count", 0)),
        ("Review", summary.get("daily_review_item_count", 0)),
    ]
    chip_html = "\n".join(
        f"<li><strong>{escape(label)}</strong><span>{escape(str(value))}</span></li>"
        for label, value in chips
    )
    events_html = _render_quality_events(
        _list_of_mappings(quality_report.get("events"))[:8]
    ).strip()
    review_html = _render_quality_review(
        _list_of_mappings(quality_report.get("daily_review_items"))[:8]
    ).strip()
    return f"""
<section id="queue-quality" style="margin:32px 0;padding:24px;border:1px solid #d7dde8;border-radius:8px;background:#f7fafc;color:#172033;">
  <h2 style="margin:0 0 12px;font-size:1.35rem;">Queue Quality</h2>
  <p style="margin:0 0 16px;">Operational queue observations, canonical targets, and review gaps from the latest quality contract.</p>
  <ul style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;list-style:none;padding:0;margin:0 0 18px;">
    {chip_html}
  </ul>
  <h3 style="margin:20px 0 10px;font-size:1.05rem;">Tracked Events</h3>
  {events_html}
  <h3 style="margin:20px 0 10px;font-size:1.05rem;">Daily Review</h3>
  {review_html}
</section>"""


def _render_quality_events(events: list[Mapping[str, Any]]) -> str:
    if not events:
        return "<p>No tracked queue quality events were generated.</p>"
    rows = []
    for event in events:
        rows.append(
            "<tr>"
            f"<td>{escape(str(event.get('event_model') or ''))}</td>"
            f"<td>{escape(str(event.get('source') or ''))}</td>"
            f"<td>{escape(str(event.get('attraction_name') or event.get('title') or ''))}</td>"
            f"<td>{escape(str(event.get('wait_minutes') if event.get('wait_minutes') is not None else ''))}</td>"
            f"<td>{escape(str(event.get('availability_status') or ''))}</td>"
            f"<td><code>{escape(str(event.get('canonical_key') or ''))}</code></td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return f"""
<div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:.92rem;">
    <thead><tr><th>Model</th><th>Source</th><th>Target</th><th>Wait</th><th>Status</th><th>Canonical Key</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>"""


def _render_quality_review(items: list[Mapping[str, Any]]) -> str:
    if not items:
        return "<p>No queue quality review items.</p>"
    rendered = []
    for item in items:
        reason = escape(str(item.get("reason") or "review"))
        source = escape(str(item.get("source") or item.get("event_model") or ""))
        detail = escape(str(item.get("canonical_key") or item.get("activation_gate") or item.get("title") or ""))
        rendered.append(f"<li><strong>{reason}</strong> {source} <span>{detail}</span></li>")
    return f"<ul>{''.join(rendered)}</ul>"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
