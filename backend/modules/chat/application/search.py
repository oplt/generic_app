from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchOptions:
    max_results: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class SearchFetchOptions:
    """Hard limits for optional source-page retrieval."""

    timeout_seconds: float
    max_content_bytes: int


@dataclass(frozen=True, slots=True)
class SearchResult:
    provider_id: str
    title: str
    url: str
    snippet: str
    published_at: str | None
    rank: int


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """Normalized, bounded page content returned by a search provider."""

    provider_id: str
    title: str
    url: str
    text: str
    published_at: str | None
    rank: int
    metadata: dict[str, str | int | float | bool]


class SearchProviderError(RuntimeError):
    """Safe provider failure without exposing response bodies or credentials."""


class SearchProvider(Protocol):
    async def search(self, query: str, options: SearchOptions) -> list[SearchResult]: ...

    async def fetch(
        self, result: SearchResult, options: SearchFetchOptions
    ) -> SearchDocument: ...
