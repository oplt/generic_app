from __future__ import annotations


class PgVectorUnavailableError(RuntimeError):
    """Raised when pgvector cannot serve an indexed retrieval request."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"pgvector retrieval is unavailable: {reason}")
