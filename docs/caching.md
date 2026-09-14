# Application caching

Shared caching for feature modules lives in `backend/lib/app_cache/`. Prefer
`app_cache` for new code. Redis transport, local hot-key TTL, and fail-open
semantics remain in `backend/core/cache.py`.

## API

```python
from backend.lib.app_cache import CacheScope, app_cache, namespaces

key = app_cache.key(
    namespaces.PERMISSIONS,
    "project_read",
    scope=CacheScope(organization_id=org_id, user_id=user_id, project_id=project_id),
)

await app_cache.get(key)
await app_cache.set(key, payload, ttl_seconds=60, tags=[f"permissions:org:{org_id}"])
await app_cache.delete(key)
await app_cache.invalidate_tags(f"permissions:org:{org_id}")
await app_cache.get_or_set(key, loader, ttl_seconds=60, cache_none=True)
```

Key shape:

`ga:{version}:{namespace}:org:…:user:…:project:…:{parts…}`

Hash long or sensitive material with `app_cache.hash(...)` / `hash_cache_part`
before placing it in a key. Do not put raw queries, tokens, or PII in key segments.

## Namespaces

Fixed strings in `backend.lib.app_cache.namespaces` (auth, settings, feature_flags,
embeddings, retrieval, permissions, api_metadata, platform, memory, generation).
Use these only so Prometheus labels stay low-cardinality.

## Semantics

| Concern | Behavior |
| --- | --- |
| Backend | Redis via `REDIS_URL`; optional process-local TTL for hot platform keys |
| Fail-open | Redis errors → miss on read, soft no-op on write |
| Negative cache | Sentinel payload; `get` / `get_or_set` return `None` |
| Single-flight | In-process lock + Redis NX lock via `coordinated_cache_load` |
| Tags | Redis sets under `ga:tag:{tag}`; `invalidate_tags` deletes members |
| Generations | Retrieval still uses generation counters for corpus/user invalidation |

## Migrated helpers

- `backend/lib/retrieval_cache.py` — get/set through `app_cache`; generation bumps unchanged; writes also register org/user/project tags
- `backend/lib/embedding_cache.py` — batch get/set through `app_cache`

Legacy `cache_get_json` / `cache_set_json` remain valid for platform/settings hot paths.

## Metrics

App-cache layer (low-cardinality labels only):

- `cache_writes_total{namespace,outcome}`
- `cache_operation_latency_seconds{namespace,operation}`
- `cache_negative_hits_total{namespace}`
- `cache_tag_invalidations_total{outcome}`

Core Redis layer still emits `cache_hits_total`, `cache_misses_total`,
`cache_errors_total`, and loader single-flight counters.
