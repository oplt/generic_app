from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.observability import prometheus_metrics

POOL_LABEL = "primary"


def _update_pool_metrics(pool) -> None:
    prometheus_metrics.db_pool_checked_out.labels(POOL_LABEL).set(pool.checkedout())
    prometheus_metrics.db_pool_size.labels(POOL_LABEL).set(pool.size())
    prometheus_metrics.db_pool_overflow.labels(POOL_LABEL).set(max(pool.overflow(), 0))


def _engine_options() -> dict[str, object]:
    return {
        "pool_pre_ping": True,
        "future": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT_SECONDS,
        "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
        "connect_args": {
            "timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
            "command_timeout": settings.DB_COMMAND_TIMEOUT_SECONDS,
            "server_settings": {
                "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
                "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
                "idle_in_transaction_session_timeout": str(
                    settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS
                ),
            },
        },
    }


engine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_options(),
)


@event.listens_for(engine.sync_engine, "checkout")
def _record_pool_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
    del dbapi_connection, connection_record, connection_proxy
    pool = engine.sync_engine.pool
    prometheus_metrics.db_pool_checkout_total.labels(POOL_LABEL).inc()
    _update_pool_metrics(pool)


@event.listens_for(engine.sync_engine, "checkin")
def _record_pool_checkin(dbapi_connection, connection_record) -> None:
    del dbapi_connection, connection_record
    _update_pool_metrics(engine.sync_engine.pool)


_update_pool_metrics(engine.sync_engine.pool)


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
