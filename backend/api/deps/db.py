from collections.abc import AsyncGenerator

from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from backend.db.session import SessionLocal
from backend.db.transaction import rollback_safely
from backend.observability import prometheus_metrics


async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        try:
            # API use cases own commits in their route/service boundary. The
            # dependency owns session cleanup and rolls back failed requests.
            yield session
        except SQLAlchemyTimeoutError:
            prometheus_metrics.db_pool_checkout_errors_total.labels("primary").inc()
            await rollback_safely(session, owner="api.request")
            raise
        except Exception:
            await rollback_safely(session, owner="api.request")
            raise
