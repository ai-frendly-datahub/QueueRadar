# QUEUERADAR

공공 시설(병원, 관공서, 은행 등)의 실시간 대기열 정보를 수집하고 대기 시간 트렌드를 분석합니다.

## STRUCTURE

```
QueueRadar/
├── queueradar/
│   ├── collector.py              # collect_sources() — Queue Times API 및 공공 시설 API
│   ├── analyzer.py               # apply_entity_rules() — 시설 유형별 키워드 매칭 (병원, 관공서, 은행 등)
│   ├── reporter.py               # generate_report() — Jinja2 HTML
│   ├── storage.py                # RadarStorage — DuckDB upsert/query/retention
│   ├── models.py                 # Source, Article, EntityDefinition, CategoryConfig
│   ├── config_loader.py          # YAML 로딩
│   ├── logger.py                 # structlog 구조화 로깅
│   ├── notifier.py               # Email/Webhook 알림
│   ├── raw_logger.py             # JSONL 원시 로깅
│   ├── search_index.py           # SQLite FTS5 전문 검색
│   ├── nl_query.py               # 자연어 쿼리 파서
│   ├── common/                   # 공유 유틸리티
│   └── mcp_server/               # MCP 서버 (server.py + tools.py)
├── config/
│   ├── config.yaml               # database_path, report_dir, raw_data_dir, search_db_path
│   └── categories/queue.yaml  # 소스 + 엔티티 정의
├── data/                         # DuckDB, search_index.db, raw/ JSONL
├── reports/                      # 생성된 HTML 리포트
├── tests/unit/                   # pytest 단위 테스트
├── main.py                       # CLI 엔트리포인트
└── .github/workflows/radar-crawler.yml
```

## ENTITIES

| Entity | Examples |
|--------|----------|
| WaitTime | wait time, queue, line, 대기 |
| Attraction | ride, roller coaster, 놀이기구 |
| Status | open, closed, 운영 상태 |
| Location | Disney, Universal, park, 공원 |

## DEVIATIONS FROM TEMPLATE

- Queue Times API 기반 실시간 대기시간 snapshot을 핵심 source로 취급한다.
- `observed_at`, `collected_at`, timezone, stale reading을 분리해 품질 리포트에 남긴다.
- 예약 슬롯, 티켓 가격, 날씨 context는 대기시간과 별도 이벤트 모델로 유지한다.

## COMMANDS

```bash
python main.py --category queue --recent-days 7
python main.py --category queue --per-source-limit 50 --keep-days 90
```
