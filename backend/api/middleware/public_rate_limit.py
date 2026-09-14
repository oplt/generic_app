from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from backend.core.config import settings
from backend.core.rate_limit import check_rate_limit


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if settings.PUBLIC_RATE_LIMIT_REQUESTS <= 0:
            return await call_next(request)

        if not request.url.path.startswith("/api/") and not request.url.path.startswith("/health/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:public:{client_ip}"
        try:
            await check_rate_limit(
                key,
                settings.PUBLIC_RATE_LIMIT_REQUESTS,
                settings.PUBLIC_RATE_LIMIT_WINDOW_SECONDS,
            )
        except HTTPException as exc:
            if exc.status_code == 429:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            raise

        return await call_next(request)
