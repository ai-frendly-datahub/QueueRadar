# QueueRadar

QueueRadar is a lightweight Radar project for tracking queue and reservation trends.
It collects RSS articles, tags queue-related entities, stores data in DuckDB, builds an
SQLite FTS5 search index, and generates an HTML report.

## What It Tracks

- Wait times and queue systems
- Reservation and appointment scheduling
- No-show and cancellation fee policies
- Reservation platforms
- Healthcare appointment trends

## Quick Start

```bash
pip install -r requirements.txt
python main.py --category queue --recent-days 7
```

Generated outputs:

- Report: `reports/queue_report.html`
- DuckDB: `data/radar_data.duckdb`
- Raw JSONL: `data/raw/`
- FTS5 index: `data/search_index.db`

## Configuration

- Global settings: `config/config.yaml`
- Queue category: `config/categories/queue.yaml`
- Category template: `config/categories/_template.yaml`

## MCP Server

Package: `queueradar/mcp_server/`

Included tools:

- `search`
- `recent_updates`
- `sql`
- `top_trends`
- `queue_status`

Run server entrypoint module:

```bash
python -m queueradar.mcp_server.server
```

## Tests

```bash
pytest tests/ -v
```

## CI/CD

Workflow: `.github/workflows/radar-crawler.yml`

- Name: `QueueRadar Crawler`
- Category env: `RADAR_CATEGORY: queue`
- Runs daily and on manual dispatch
- Publishes `reports/` to `gh-pages`
