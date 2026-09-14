import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.errors import StructuredApiError

logger = logging.getLogger("backend.error")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "request_validation_failed path=%s correlation_id=%s errors=%s",
            request.url.path,
            getattr(request.state, "correlation_id", None),
            len(exc.errors()),
        )
        if request.url.path.startswith("/api/v1/chat"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Chat request validation failed.",
                    "error": {
                        "code": "invalid_request",
                        "message": "Chat request validation failed.",
                        "retryable": False,
                        "details": {},
                    },
                    "error_code": "invalid_request",
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
            )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": exc.errors(),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        logger.warning(
            "value_error path=%s correlation_id=%s detail=%s",
            request.url.path,
            getattr(request.state, "correlation_id", None),
            str(exc)[:200],
        )
        return JSONResponse(
            status_code=400,
            content={
                "detail": "The request contains invalid data.",
                "error_code": "invalid_request",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            logger.error(
                "http_exception path=%s status=%s correlation_id=%s detail=%s",
                request.url.path,
                exc.status_code,
                getattr(request.state, "correlation_id", None),
                str(exc.detail)[:200],
            )
        elif exc.status_code >= 400:
            logger.warning(
                "http_exception path=%s status=%s correlation_id=%s detail=%s",
                request.url.path,
                exc.status_code,
                getattr(request.state, "correlation_id", None),
                str(exc.detail)[:200],
            )
        is_chat_error = request.url.path.startswith("/api/v1/chat")
        if isinstance(exc, StructuredApiError) or is_chat_error:
            code = (
                exc.code
                if isinstance(exc, StructuredApiError)
                else {
                    401: "unauthorized",
                    403: "unauthorized",
                    404: "not_found",
                    409: "conflict",
                    413: "message_too_large",
                    422: "invalid_request",
                    429: "rate_limited",
                    503: "provider_unavailable",
                }.get(exc.status_code, "internal_error")
            )
            message = exc.message if isinstance(exc, StructuredApiError) else "Chat request failed."
            retryable = (
                exc.retryable
                if isinstance(exc, StructuredApiError)
                else exc.status_code in {429, 502, 503, 504}
            )
            details = exc.details if isinstance(exc, StructuredApiError) else {}
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": message,
                    "error": {
                        "code": code,
                        "message": message,
                        "retryable": retryable,
                        "details": details,
                    },
                    "error_code": code,
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
                headers=exc.headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled_exception path=%s correlation_id=%s",
            request.url.path,
            getattr(request.state, "correlation_id", None),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
