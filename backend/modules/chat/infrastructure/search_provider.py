from __future__ import annotations

import html
import ipaddress
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from backend.core.config import settings
from backend.modules.chat.application.query_router import sanitize_search_query
from backend.modules.chat.application.search import (
    SearchDocument,
    SearchFetchOptions,
    SearchOptions,
    SearchProvider,
    SearchProviderError,
    SearchResult,
)


class GenericJsonSearchProvider(SearchProvider):
    """Adapter for a configured JSON search endpoint.

    The endpoint contract is intentionally small: ``results`` (or ``organic``)
    is an array containing title, url/link, and snippet/description fields.
    Provider-specific credentials stay in settings and never enter domain code.
    """

    async def search(self, query: str, options: SearchOptions) -> list[SearchResult]:
        if not settings.WEB_SEARCH_BASE_URL or not settings.WEB_SEARCH_API_KEY:
            raise SearchProviderError("search_credentials_missing")
        query = sanitize_search_query(query)
        try:
            timeout = httpx.Timeout(options.timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "GET",
                    settings.WEB_SEARCH_BASE_URL,
                    params={"q": query, "limit": options.max_results},
                    headers={"Authorization": f"Bearer {settings.WEB_SEARCH_API_KEY}"},
                ) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > settings.WEB_SEARCH_MAX_CONTENT_BYTES:
                            raise SearchProviderError("search_response_too_large")
                        chunks.append(chunk)
                payload = json.loads(b"".join(chunks))
        except SearchProviderError:
            raise
        except (httpx.TimeoutException, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise SearchProviderError("search_request_failed") from exc

        raw_results = payload.get("results") or payload.get("organic") or []
        if not isinstance(raw_results, list):
            raise SearchProviderError("search_response_invalid")
        results: list[SearchResult] = []
        for index, item in enumerate(raw_results[: options.max_results], start=1):
            if not isinstance(item, dict):
                continue
            normalized = self._normalize(item, index)
            if normalized:
                results.append(normalized)
        return results

    async def fetch(self, result: SearchResult, options: SearchFetchOptions) -> SearchDocument:
        """Fetch one public text page with strict byte/time limits.

        This is deliberately a plain HTTP adapter: no JavaScript, crawling,
        redirects, credentials, or provider API key are involved. Page text is
        untrusted evidence and callers must label it before adding it to a
        model context.
        """

        url = _safe_fetch_url(result.url)
        try:
            timeout = httpx.Timeout(options.timeout_seconds)
            async with (
                httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client,
                client.stream(
                    "GET",
                    url,
                    headers={"Accept": "text/html,text/plain;q=0.9,application/json;q=0.5"},
                ) as response,
            ):
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(
                    value in content_type
                    for value in ("text/", "application/json", "application/xml")
                ):
                    raise SearchProviderError("search_document_type_unsupported")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > options.max_content_bytes:
                        raise SearchProviderError("search_document_too_large")
                    chunks.append(chunk)
        except SearchProviderError:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise SearchProviderError("search_document_fetch_failed") from exc

        raw_text = b"".join(chunks).decode("utf-8", errors="replace")
        text = _extract_text(raw_text, content_type)
        if not text:
            raise SearchProviderError("search_document_empty")
        return SearchDocument(
            provider_id=result.provider_id,
            title=result.title,
            url=url,
            text=text,
            published_at=result.published_at,
            rank=result.rank,
            metadata={"untrusted": True, "content_type": content_type or "unknown"},
        )

    @staticmethod
    def _normalize(item: dict[str, Any], rank: int) -> SearchResult | None:
        title = _clean_text(item.get("title"), 512)
        url = _safe_result_url(str(item.get("url") or item.get("link") or ""))
        snippet = _clean_text(item.get("snippet") or item.get("description"), 2000)
        if not title or not url or not snippet:
            return None
        return SearchResult(
            provider_id=_clean_text(item.get("id") or item.get("source_id") or rank, 128),
            title=title,
            url=url,
            snippet=snippet,
            published_at=(
                _clean_text(item["published_at"], 64) if item.get("published_at") else None
            ),
            rank=rank,
        )


def build_search_provider() -> SearchProvider:
    if settings.WEB_SEARCH_PROVIDER != "generic_json":
        raise SearchProviderError("search_provider_not_supported")
    return GenericJsonSearchProvider()


class _VisibleTextParser(HTMLParser):
    _IGNORED_TAGS = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._IGNORED_TAGS:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _extract_text(raw_text: str, content_type: str) -> str:
    if "html" in content_type or "xhtml" in content_type:
        parser = _VisibleTextParser()
        try:
            parser.feed(raw_text)
            raw_text = " ".join(parser.parts)
        except ValueError:
            raw_text = html.unescape(raw_text)
    return _clean_text(raw_text, 16_000)


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _safe_result_url(value: str) -> str:
    try:
        parsed = urlparse(value.strip()[:2048])
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return ""
        if parsed.username or parsed.password or not parsed.hostname:
            return ""
    except ValueError:
        return ""
    # Fragments are client-only and should not be persisted as citation identity.
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.params, parsed.query, "")
    )


def _safe_fetch_url(value: str) -> str:
    url = _safe_result_url(value)
    if not url:
        raise SearchProviderError("search_result_url_invalid")
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise SearchProviderError("search_result_url_private")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        raise SearchProviderError("search_result_url_private")
    return url
