import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.modules.chat.application.query_router import QueryRouter, sanitize_search_query
from backend.modules.chat.application.search import SearchDocument, SearchResult
from backend.modules.chat.infrastructure.search_provider import (
    GenericJsonSearchProvider,
    _extract_text,
)
from backend.modules.chat.schemas import ChatMessageRequest
from backend.modules.chat.tests.test_service import build_service


class QueryRouterTest(unittest.TestCase):
    def setUp(self):
        self.router = QueryRouter()

    def test_explicit_general_uses_memory_but_never_web(self):
        decision = self.router.decide(
            mode="general",
            query="Help me plan my week",
            selected_document_ids=[],
            memory_enabled=True,
            web_enabled=True,
        )

        self.assertEqual(decision.mode, "general")
        self.assertTrue(decision.use_memory)
        self.assertFalse(decision.use_web)

    def test_auto_current_question_uses_web_only_when_enabled(self):
        enabled = self.router.decide(
            mode="auto",
            query="What is the latest price today?",
            selected_document_ids=["private-doc"],
            memory_enabled=True,
            web_enabled=True,
        )
        disabled = self.router.decide(
            mode="auto",
            query="What is the latest price today?",
            selected_document_ids=["private-doc"],
            memory_enabled=True,
            web_enabled=False,
        )

        self.assertTrue(enabled.use_web)
        self.assertFalse(enabled.use_documents)
        self.assertEqual(disabled.reason, "fallback")
        self.assertEqual(disabled.mode, "general")

    def test_auto_document_question_uses_selected_documents(self):
        decision = self.router.decide(
            mode="auto",
            query="What does the selected policy say about leave?",
            selected_document_ids=["doc-1"],
            memory_enabled=True,
            web_enabled=True,
        )

        self.assertTrue(decision.use_documents)
        self.assertFalse(decision.use_web)
        self.assertEqual(decision.reason, "selected_documents")

    def test_auto_direct_web_request_has_explicit_route_reason(self):
        decision = self.router.decide(
            mode="auto",
            query="Search the web for the latest release notes",
            selected_document_ids=[],
            memory_enabled=False,
            web_enabled=True,
        )

        self.assertEqual(decision.mode, "web")
        self.assertEqual(decision.reason, "direct_web_request")
        self.assertTrue(decision.use_web)
        self.assertFalse(decision.use_memory)

    def test_auto_direct_web_request_without_provider_uses_safe_general_fallback(self):
        decision = self.router.decide(
            mode="auto",
            query="Search the internet for current release notes",
            selected_document_ids=[],
            memory_enabled=False,
            web_enabled=False,
        )

        self.assertEqual(decision.mode, "general")
        self.assertEqual(decision.reason, "fallback")
        self.assertEqual(decision.confidence, "low")
        self.assertFalse(decision.use_memory)

    def test_search_query_is_bounded_and_control_characters_are_removed(self):
        query = sanitize_search_query("latest\nprice\x00" + (" x" * 300))

        self.assertNotIn("\x00", query)
        self.assertLessEqual(len(query), 400)


class SearchProviderNormalizationTest(unittest.TestCase):
    def test_normalizes_common_json_result_shape(self):
        result = GenericJsonSearchProvider._normalize(
            {
                "id": "result-1",
                "title": "Example",
                "link": "https://example.test",
                "description": "Snippet",
            },
            1,
        )

        self.assertEqual(
            result,
            SearchResult(
                "result-1",
                "Example",
                "https://example.test",
                "Snippet",
                None,
                1,
            ),
        )

    def test_rejects_non_http_result_urls(self):
        self.assertIsNone(
            GenericJsonSearchProvider._normalize(
                {"title": "Unsafe", "url": "javascript:alert(1)", "snippet": "x"},
                1,
            )
        )

    def test_extracts_visible_text_without_active_content(self):
        self.assertEqual(
            _extract_text(
                "<html><script>ignore()</script><p>Hello&nbsp;world</p></html>",
                "text/html",
            ),
            "Hello world",
        )

    def test_search_document_contract_keeps_untrusted_metadata(self):
        document = SearchDocument(
            provider_id="p1",
            title="Title",
            url="https://example.test/",
            text="Untrusted text",
            published_at="2026-07-12",
            rank=1,
            metadata={"untrusted": True},
        )
        self.assertTrue(document.metadata["untrusted"])


class GeneralAndWebChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_general_mode_uses_generation_without_document_retrieval(self):
        service = build_service()
        service.memory = SimpleNamespace(
            recall_for_prompt=AsyncMock(return_value=("", [], False))
        )
        service.router = QueryRouter()
        conversation = SimpleNamespace(
            id="conversation-1",
            user_id="user-1",
            project_id=None,
            mode="general",
            memory_enabled=True,
            memory_write_enabled=False,
        )
        user = SimpleNamespace(id="user-1")

        events = [
            event
            async for event in service.stream_chat_answer(
                user,
                conversation,
                ChatMessageRequest(content="Help me write a checklist", mode="general"),
            )
        ]

        self.assertEqual(events[-1].event, "final")
        self.assertEqual(events[-1].route.mode, "general")
        service.retrieval.retrieve.assert_not_awaited()

    async def test_explicit_web_mode_returns_normalized_web_source(self):
        service = build_service()
        service.memory = SimpleNamespace(
            recall_for_prompt=AsyncMock(return_value=("", [], False))
        )
        service.router = QueryRouter()
        provider = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    SearchResult(
                        "web-1",
                        "Public result",
                        "https://example.test",
                        "Public snippet",
                        "2026-07-12",
                        1,
                    )
                ]
            )
        )
        conversation = SimpleNamespace(
            id="conversation-1",
            user_id="user-1",
            project_id=None,
            mode="web",
            memory_enabled=True,
            memory_write_enabled=False,
        )
        user = SimpleNamespace(id="user-1")

        with patch("backend.modules.chat.service.settings.WEB_SEARCH_ENABLED", True), patch(
            "backend.modules.chat.service.build_search_provider", return_value=provider
        ):
            events = [
                event
                async for event in service.stream_chat_answer(
                    user,
                    conversation,
                    ChatMessageRequest(content="Find public information", mode="web"),
                )
            ]

        self.assertEqual(events[-1].event, "final")
        self.assertEqual(events[-1].sources[0].kind, "web")
        self.assertEqual(events[-1].sources[0].rank, 1)
        self.assertEqual(events[-1].sources[0].published_at, "2026-07-12")
        self.assertEqual(provider.search.await_args.args[0], "Find public information")
