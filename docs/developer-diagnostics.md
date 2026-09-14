# Developer diagnostics mode (Phase 15)

Flag (default **false**):

```text
DEVELOPER_DIAGNOSTICS_ENABLED=false
```

When enabled, each authenticated API request can publish a safe per-request summary:

* response header `X-Developer-Diagnostics` (JSON, no bodies)
* in-memory recent ring buffer via `GET /api/v1/developer/diagnostics/recent`
* floating UI panel mounted in `AppLayout` (shell embed; **not** a primary router page)
* visible only when the status endpoint reports `enabled: true` (`DEVELOPER_DIAGNOSTICS_ENABLED`)
* module manifest: `surface=embedded`, `embedding_host=app.shell`

## Captured fields

| Area | Fields |
| --- | --- |
| Request | method, path, status, duration_ms, correlation_id, trace_id |
| DB | sql_query_count, db_duration_ms (SQLAlchemy listeners; no SQL text) |
| Cache | hits / misses |
| External APIs | provider + operation + optional latency (from OTEL-friendly hooks) |
| RAG | stage labels, retrieved chunk count |
| Tasks | Celery / eager job names spawned during the request |

## Safety

* Disabled by default; production stays off unless explicitly enabled
* Never captures request/response bodies, SQL statements, or credentials
* Production recent endpoint requires `diagnostics.read`

## Tempo / Grafana

Status payload includes `tempo_explore_url` / `grafana_base_url` when configured.
The panel deep-links with the latest `trace_id` / `correlation_id`.

## Related

* Infra diagnostics: [diagnostics.md](diagnostics.md)
* Observability UI: `/observability`
