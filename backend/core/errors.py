from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class StructuredApiError(HTTPException):
    """HTTP error with safe, machine-readable client contract."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
