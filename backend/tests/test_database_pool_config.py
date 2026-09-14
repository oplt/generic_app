import pytest
from pydantic import ValidationError

from backend.core.config import settings
from backend.db import session as db_session


def _settings_with(**overrides):
    payload = settings.model_dump()
    payload.update(overrides)
    return settings.__class__.model_validate(payload)


def test_database_pool_defaults_are_bounded_and_exposed():
    assert settings.DB_POOL_SIZE == 10
    assert settings.DB_MAX_OVERFLOW == 10
    assert settings.DB_POOL_TIMEOUT_SECONDS == 30
    assert settings.DB_POOL_RECYCLE_SECONDS == 1800
    assert settings.DB_CONNECT_TIMEOUT_SECONDS == 5
    assert settings.DB_COMMAND_TIMEOUT_SECONDS == 60
    assert settings.DB_STATEMENT_TIMEOUT_MS == 30000
    assert settings.DB_LOCK_TIMEOUT_MS == 5000
    assert settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS == 60000
    assert settings.OUTBOX_DISPATCH_LEASE_SECONDS == 600


def test_database_engine_options_apply_pool_and_postgres_timeouts():
    options = db_session._engine_options()

    assert options["pool_size"] == settings.DB_POOL_SIZE
    assert options["max_overflow"] == settings.DB_MAX_OVERFLOW
    assert options["pool_timeout"] == settings.DB_POOL_TIMEOUT_SECONDS
    assert options["pool_recycle"] == settings.DB_POOL_RECYCLE_SECONDS
    assert options["connect_args"] == {
        "timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
        "command_timeout": settings.DB_COMMAND_TIMEOUT_SECONDS,
        "server_settings": {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
            "idle_in_transaction_session_timeout": str(
                settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS
            ),
        },
    }

    pool = db_session.engine.sync_engine.pool
    assert pool.size() == settings.DB_POOL_SIZE
    assert pool._max_overflow == settings.DB_MAX_OVERFLOW
    assert pool._timeout == settings.DB_POOL_TIMEOUT_SECONDS
    assert pool._recycle == settings.DB_POOL_RECYCLE_SECONDS


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("DB_POOL_SIZE", 0, "DB_POOL_SIZE"),
        ("DB_MAX_OVERFLOW", -1, "DB_MAX_OVERFLOW"),
        ("DB_POOL_TIMEOUT_SECONDS", 0, "DB_POOL_TIMEOUT_SECONDS"),
        ("DB_CONNECT_TIMEOUT_SECONDS", 0, "DB_CONNECT_TIMEOUT_SECONDS"),
        ("DB_COMMAND_TIMEOUT_SECONDS", 0, "DB_COMMAND_TIMEOUT_SECONDS"),
        ("DB_STATEMENT_TIMEOUT_MS", 0, "DB_STATEMENT_TIMEOUT_MS"),
        ("DB_LOCK_TIMEOUT_MS", 0, "DB_LOCK_TIMEOUT_MS"),
        ("OUTBOX_DISPATCH_LEASE_SECONDS", 0, "OUTBOX_DISPATCH_LEASE_SECONDS"),
        (
            "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS",
            0,
            "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS",
        ),
    ],
)
def test_invalid_database_pool_or_timeout_values_fail_validation(field, value, message):
    with pytest.raises(ValidationError, match=message):
        _settings_with(**{field: value})


def test_database_pool_capacity_is_bounded():
    with pytest.raises(ValidationError, match=r"DB_POOL_SIZE \+ DB_MAX_OVERFLOW"):
        _settings_with(DB_POOL_SIZE=100, DB_MAX_OVERFLOW=151)
