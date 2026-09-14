# API / query bottleneck audit (Phase 4.4)

Scope: repositories and hot API paths. Prefer existing helpers in
`backend/lib/concurrency.py` and `backend/core/cache.py`.

## Findings

| Area | Risk | Verdict | Action |
| --- | --- | --- | --- |
| `worker_readiness` × N API replicas | Celery inspect broadcast + DB aggregate + multi `LLEN` every 30s | **Material** under multi-replica | Shared Redis cache (TTL 25s) + timing histogram; queues scoped to active modules |
| `_required_queues` always included memory/eval/… | Core profile falsely needs specialist workers | **Bug / false ready=503** | Use `active_celery_queues` + default/email |
| Admin `/metrics` | 4 COUNT round-trips | Low but clear | Collapse user aggregates to 1 SELECT (+ notifications) |
| Policy roles/permissions list | Unbounded `.all()` | OK | Catalog is small/static; no pagination needed |
| Admin audit logs | Unbounded | Mitigated | Hard `limit=100` |
| Projects / notifications / jobs lists | Pagination | OK | Existing page/cursor helpers |
| AI overview coordinator | Parallel gathers | OK | Bounded limits via `DEFAULT_PAGE_LIMIT` |
| Memory / RAG retrieve | Fan-out | OK | Already on `bounded_gather` / `map_concurrently` |
| Storage boto3 | Sync SDK | OK | Wrapped in `asyncio.to_thread` |
| Policy authorize | Repeated resolve | OK | `app_cache` permissions TTL 60s |

## Optimizations shipped this phase

1. Worker readiness shared cache + active-queue set + `worker_readiness_probe_duration_seconds`
2. Admin metrics user COUNT collapse

## Intentionally not changed

- Policy catalog endpoints remain unpaginated (tiny tables)
- No premature micro-opts without evidence beyond inspection above
