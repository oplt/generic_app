from __future__ import annotations

import re

from backend.modules.chat.schemas import ChatMode, ChatRouteDecision

CURRENT_INFORMATION_PATTERN = re.compile(
    r"\b(today|latest|current|recent|right now|this week|this month|this year|news|price|weather|"
    r"who is the|what happened)\b",
    re.IGNORECASE,
)
DIRECT_WEB_PATTERN = re.compile(
    r"\b(web search|search the web|search the internet|internet search|search online|"
    r"find online|look up|lookup|on the web|on the internet|"
    r"browse|google)\b",
    re.IGNORECASE,
)
DOCUMENT_PATTERN = re.compile(
    r"\b(document|file|selected|policy|according to|in the|from the|uploaded|pdf|"
    r"what does .* say|summari[sz]e)\b",
    re.IGNORECASE,
)


def sanitize_search_query(value: str, *, max_chars: int = 400) -> str:
    """Keep search input request-local and bounded; never append private context."""

    normalized = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:max_chars]


class QueryRouter:
    def decide(
        self,
        *,
        mode: ChatMode,
        query: str,
        selected_document_ids: list[str],
        memory_enabled: bool,
        web_enabled: bool,
    ) -> ChatRouteDecision:
        safe_query = sanitize_search_query(query)
        if mode == "documents":
            return ChatRouteDecision(
                mode="documents",
                reason="explicit_mode",
                confidence="high",
                use_documents=True,
                search_query=None,
            )
        if mode == "general":
            return ChatRouteDecision(
                mode="general",
                reason="explicit_mode",
                confidence="high",
                use_memory=memory_enabled,
            )
        if mode == "web":
            return ChatRouteDecision(
                mode="web",
                reason="explicit_mode",
                confidence="high",
                use_web=True,
                search_query=safe_query,
            )

        if DIRECT_WEB_PATTERN.search(query):
            if web_enabled:
                return ChatRouteDecision(
                    mode="web",
                    reason="direct_web_request",
                    confidence="high",
                    use_web=True,
                    search_query=safe_query,
                )
            return ChatRouteDecision(
                mode="general",
                reason="fallback",
                confidence="low",
                use_memory=memory_enabled,
            )
        if CURRENT_INFORMATION_PATTERN.search(query):
            if web_enabled:
                return ChatRouteDecision(
                    mode="web",
                    reason="current_information",
                    confidence="high",
                    use_web=True,
                    search_query=safe_query,
                )
            return ChatRouteDecision(
                mode="general",
                reason="fallback",
                confidence="medium",
                use_memory=memory_enabled,
            )
        if selected_document_ids and DOCUMENT_PATTERN.search(query):
            return ChatRouteDecision(
                mode="documents",
                reason="selected_documents",
                confidence="high",
                use_documents=True,
            )
        return ChatRouteDecision(
            mode="general",
            reason="general_question",
            confidence="medium",
            use_memory=memory_enabled,
        )
