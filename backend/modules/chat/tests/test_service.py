import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.lib.generation_port import RagGenerationChunk, RagGenerationResult
from backend.modules.chat.schemas import ChatConversationUpdate, ChatMessageRequest
from backend.modules.chat.service import NO_DOCUMENT_CONTEXT_ANSWER, DocumentChatService
from backend.modules.rag.application.citation_service import CitationService
from backend.modules.rag.application.rag_context_builder import RagContextBuilder
from backend.modules.rag.domain.models import RetrievalOutcome, RetrievedChunk


class FakeGeneration:
    def __init__(self):
        self.calls = []

    async def run_rag_answer(self, user, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="run-1",
            output_text="The answer is grounded. [Source 1]",
            model_name="local",
        )


class StreamingGeneration:
    async def stream_rag_answer(self, user, **kwargs):
        yield RagGenerationChunk(text="first ")
        yield RagGenerationChunk(
            text="second",
            result=RagGenerationResult(id="run-1", output_text=None, model_name="local"),
        )


def build_service(*, chunks=None, indexed=None):
    service = DocumentChatService.__new__(DocumentChatService)
    service.db = AsyncMock()
    service.repo = MagicMock()
    service.rag_repo = MagicMock()
    service.retrieval = MagicMock()
    service.generation = FakeGeneration()
    service.citations = CitationService()
    service.context_builder = RagContextBuilder(service.citations)
    service.rag_repo.list_indexed_documents = AsyncMock(
        return_value=indexed if indexed is not None else [SimpleNamespace(id="doc-1")]
    )
    service.retrieval.retrieve = AsyncMock(
        return_value=RetrievalOutcome(chunks=chunks or [])
    )
    service.repo.create_message = AsyncMock(
        side_effect=[
            SimpleNamespace(id="user-message", role="user"),
            SimpleNamespace(
                id="assistant-message",
                role="assistant",
                content="",
                status="generating",
            ),
        ]
    )
    service.repo.touch_conversation = AsyncMock()
    service.repo.create_sources = AsyncMock()
    service.db.commit = AsyncMock()
    service.repo.get_conversation_for_user = AsyncMock()
    return service


class DocumentChatServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_generation_deltas_are_forwarded_without_waiting_for_full_answer(self):
        service = build_service()
        service.generation = StreamingGeneration()

        events = [
            event
            async for event in service._iter_generation_events(
                SimpleNamespace(id="user-1"),
                is_disconnected=None,
                query="question",
                combined_context="context",
                retrieved_chunk_ids=[],
            )
        ]

        self.assertEqual([event.text for event in events], ["first ", "second"])
        self.assertEqual(events[-1].result.id, "run-1")

    def test_token_batches_are_bounded(self):
        batches = DocumentChatService._bounded_token_batches("word " * 100)

        self.assertGreater(len(batches), 1)
        self.assertTrue(all(len(batch) <= 256 for batch in batches))
        self.assertEqual("".join(batches), "word " * 100)

    async def test_disconnect_marks_pending_assistant_as_cancelled(self):
        service = build_service(chunks=[])
        conversation = SimpleNamespace(
            id="conversation-1", user_id="user-1", project_id=None, mode="documents"
        )
        user = SimpleNamespace(id="user-1")

        with self.assertRaises(asyncio.CancelledError):
            async for _ in service.stream_document_answer(
                user,
                conversation,
                ChatMessageRequest(
                    content="Stop this request",
                    mode="documents",
                    document_ids=["doc-1"],
                ),
                is_disconnected=AsyncMock(return_value=True),
            ):
                pass

        self.assertEqual(
            service.repo.create_message.await_args_list[1].kwargs["status"],
            "generating",
        )
        self.assertTrue(service.db.commit.await_count >= 2)

    async def test_strict_documents_mode_never_calls_memory_and_persists_sources(self):
        chunk = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            content="The rollout starts on Monday.",
            score=0.9,
            filename="plan.md",
            chunk_index=0,
        )
        service = build_service(chunks=[chunk])
        conversation = SimpleNamespace(
            id="conversation-1", user_id="user-1", project_id=None, mode="documents"
        )
        user = SimpleNamespace(id="user-1")
        events = [
            event
            async for event in service.stream_document_answer(
                user,
                conversation,
                ChatMessageRequest(
                    content="When does the rollout start?",
                    mode="documents",
                    document_ids=["doc-1"],
                ),
            )
        ]

        self.assertEqual(events[-1].event, "final")
        self.assertEqual(events[-1].sources[0].document_id, "doc-1")
        self.assertEqual(len(service.generation.calls), 1)
        self.assertNotIn("memory", service.generation.calls[0]["combined_context"].lower())
        service.repo.create_sources.assert_awaited_once()

    async def test_no_context_returns_explicit_no_answer_without_generation(self):
        service = build_service(chunks=[])
        conversation = SimpleNamespace(
            id="conversation-1", user_id="user-1", project_id=None, mode="documents"
        )
        user = SimpleNamespace(id="user-1")
        events = [
            event
            async for event in service.stream_document_answer(
                user,
                conversation,
                ChatMessageRequest(
                    content="What is missing?",
                    mode="documents",
                    document_ids=["doc-1"],
                ),
            )
        ]

        self.assertEqual(events[-1].event, "final")
        self.assertEqual(events[-1].answer, NO_DOCUMENT_CONTEXT_ANSWER)
        self.assertEqual(service.generation.calls, [])

    async def test_unowned_or_unindexed_document_selection_is_rejected(self):
        service = build_service(indexed=[])
        conversation = SimpleNamespace(
            id="conversation-1", user_id="user-1", project_id=None, mode="documents"
        )
        user = SimpleNamespace(id="user-1")

        with self.assertRaises(Exception) as raised:
            async for _ in service.stream_document_answer(
                user,
                conversation,
                ChatMessageRequest(
                    content="Private question",
                    mode="documents",
                    document_ids=["doc-2"],
                ),
            ):
                pass

        self.assertEqual(raised.exception.status_code, 403)

    async def test_memory_controls_are_updated_on_owned_conversation(self):
        service = build_service()
        conversation = SimpleNamespace(
            id="conversation-1",
            user_id="user-1",
            project_id=None,
            mode="general",
            title="Chat",
            memory_enabled=True,
            memory_write_enabled=True,
            selected_document_ids_json="[]",
        )
        service.repo.get_conversation_for_user = AsyncMock(return_value=conversation)
        service.db.refresh = AsyncMock()

        updated = await service.update_conversation(
            SimpleNamespace(id="user-1"),
            "conversation-1",
            ChatConversationUpdate(memory_enabled=False, memory_write_enabled=False),
        )

        self.assertIs(updated, conversation)
        self.assertFalse(conversation.memory_enabled)
        self.assertFalse(conversation.memory_write_enabled)
        service.db.commit.assert_awaited()

    async def test_documents_mode_forces_memory_controls_off(self):
        service = build_service()
        conversation = SimpleNamespace(
            id="conversation-1",
            user_id="user-1",
            project_id=None,
            mode="general",
            title="Chat",
            memory_enabled=True,
            memory_write_enabled=True,
            selected_document_ids_json="[]",
        )
        service.repo.get_conversation_for_user = AsyncMock(return_value=conversation)
        service.db.refresh = AsyncMock()

        await service.update_conversation(
            SimpleNamespace(id="user-1"),
            "conversation-1",
            ChatConversationUpdate(
                mode="documents",
                memory_enabled=True,
                memory_write_enabled=True,
            ),
        )

        self.assertEqual(conversation.mode, "documents")
        self.assertFalse(conversation.memory_enabled)
        self.assertFalse(conversation.memory_write_enabled)

    async def test_clear_and_delete_are_owner_scoped(self):
        service = build_service()
        conversation = SimpleNamespace(
            id="conversation-1",
            user_id="user-1",
            project_id=None,
            mode="general",
            title="Chat",
            memory_enabled=True,
            memory_write_enabled=True,
        )
        service.repo.get_conversation_for_user = AsyncMock(return_value=conversation)
        service.repo.clear_messages = AsyncMock()
        service.repo.delete_conversation = AsyncMock()

        await service.clear_conversation(SimpleNamespace(id="user-1"), conversation.id)
        await service.delete_conversation(SimpleNamespace(id="user-1"), conversation.id)

        service.repo.clear_messages.assert_awaited_once_with(conversation.id)
        service.repo.delete_conversation.assert_awaited_once_with(conversation)
