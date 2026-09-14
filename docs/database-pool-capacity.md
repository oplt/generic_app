# PostgreSQL pool capacity and timeout baseline

The backend uses one SQLAlchemy async engine per API or worker process. Each process is
bounded by `DB_POOL_SIZE + DB_MAX_OVERFLOW`; the default is `10 + 10 = 20` connections. The
deployment capacity check is:

```text
maximum application connections =
  (API processes + worker processes) * (DB_POOL_SIZE + DB_MAX_OVERFLOW)
```

Set that value below PostgreSQL `max_connections`, leaving headroom for migrations, health
checks, monitoring, and administrative sessions. Do not increase the pool to compensate for
slow queries; fix the query or use deployment-level pooling (for example, PgBouncer) when the
measured workload requires it.

The conservative defaults are exposed in `backend/.env.example` and validated during settings
startup:

| Setting | Default | Scope |
| --- | ---: | --- |
| `DB_POOL_SIZE` | 10 | persistent connections per process |
| `DB_MAX_OVERFLOW` | 10 | temporary connections per process |
| `DB_POOL_TIMEOUT_SECONDS` | 30 | maximum checkout wait |
| `DB_POOL_RECYCLE_SECONDS` | 1800 | connection lifetime before recycle |
| `DB_CONNECT_TIMEOUT_SECONDS` | 5 | TCP/driver connection timeout |
| `DB_COMMAND_TIMEOUT_SECONDS` | 60 | asyncpg command timeout |
| `DB_STATEMENT_TIMEOUT_MS` | 30000 | PostgreSQL statement timeout |
| `DB_LOCK_TIMEOUT_MS` | 5000 | PostgreSQL lock wait timeout |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT_MS` | 60000 | PostgreSQL idle transaction timeout |

`db_pool_checked_out`, `db_pool_size`, `db_pool_overflow`, `db_pool_checkout_total`, and
`db_pool_checkout_errors_total` are available on the existing `/metrics` endpoint. A checkout
that exceeds `DB_POOL_TIMEOUT_SECONDS` raises a bounded SQLAlchemy timeout; API dependency
cleanup rolls the session back so later requests can recover.

## Reproducible 10/100-user measurements

Run the benchmark from the repository root against an isolated PostgreSQL database. It does not
read or write application data; each operation runs `SELECT 1` in a short transaction. The
command prints a human-readable summary and writes machine-readable JSON:

```sh
PYTHONPATH=. uv run --project backend python -m backend.scripts.db_pool_benchmark \
  --mode sustained --concurrency 10 --duration-seconds 60 \
  --json-output /tmp/db-pool-10.json

PYTHONPATH=. uv run --project backend python -m backend.scripts.db_pool_benchmark \
  --mode sustained --concurrency 100 --duration-seconds 60 \
  --json-output /tmp/db-pool-100.json
```

Repeat the same commands with `--mode burst` (and `--concurrency 10`/`100`) for the burst
measurement. For deliberate contention, add `--hold-seconds 0.25`. Compare success/error counts,
checkout errors, and P50/P95/P99 latency with the same PostgreSQL `max_connections` and process
counts used in deployment. Slow-query and lock behavior can be injected separately with
`pg_sleep` or a held row lock in an isolated test database; the configured server timeouts should
cap those waits at the values above.

No live PostgreSQL service was available in this checkout, so the 10/100-user measurements are
commands to run in deployment staging rather than fabricated results.
