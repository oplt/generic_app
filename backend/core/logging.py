"""Centralized application logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from backend.core.config import settings
from backend.core.log_context import get_correlation_id
from backend.core.log_handlers import (
    LOGGING_CONFIGURED_ATTR,
    attach_handlers,
)
from backend.core.log_redaction import RedactingFilter, redact_message


class CorrelationContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


_STANDARD_LOG_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Emit safe, searchable JSON while preserving correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_message(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_FIELDS or key.startswith("_"):
                continue
            if isinstance(value, str):
                payload[key] = redact_message(value)
            elif isinstance(value, str | int | float | bool) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def _build_formatter() -> logging.Formatter:
    if settings.LOG_FORMAT.lower() == "json":
        return JsonLogFormatter()
    return logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] [correlation_id=%(correlation_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def setup_logging(*, force: bool = False) -> None:
    """Configure root logging once for API, workers, and scripts."""
    root_logger = logging.getLogger()
    if getattr(root_logger, LOGGING_CONFIGURED_ATTR, False) and not force:
        root_logger.setLevel(settings.LOG_LEVEL.upper())
        return

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    root_logger.setLevel(settings.LOG_LEVEL.upper())

    formatter = _build_formatter()
    correlation_filter = CorrelationContextFilter()
    redacting_filter = RedactingFilter()

    log_file = attach_handlers(root_logger)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        handler.addFilter(correlation_filter)
        handler.addFilter(redacting_filter)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    startup_logger = logging.getLogger("backend.logging")
    if log_file is not None:
        startup_logger.info(
            "File logging enabled path=%s retention_days=%s",
            log_file,
            settings.LOG_RETENTION_DAYS,
        )
    else:
        startup_logger.info(
            "File logging disabled console=%s level=%s",
            settings.LOG_TO_CONSOLE,
            settings.LOG_LEVEL.upper(),
        )

    setattr(root_logger, LOGGING_CONFIGURED_ATTR, True)
