import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.modules.chat.repository import ChatRepository
from backend.modules.chat.schemas import ChatSource


class ChatRetentionRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_expired_conversations_are_deleted_as_a_single_scoped_statement(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=3))
        repository = ChatRepository(db)
        cutoff = datetime.now(UTC) - timedelta(days=90)

        deleted = await repository.delete_expired_conversations(cutoff)

        self.assertEqual(deleted, 3)
        db.execute.assert_awaited_once()

    async def test_create_sources_persists_contract_metadata_without_raw_aliases(self):
        db = AsyncMock()
        db.add_all = MagicMock()
        repository = ChatRepository(db)

        await repository.create_sources(
            "message-1",
            [
                ChatSource(
                    source_id="chunk-1",
                    kind="document",
                    title="Policy",
                    document_id="doc-1",
                    chunk_index=3,
                    metadata={"untrusted": True},
                ).model_dump()
            ],
        )

        row = db.add_all.call_args.args[0][0]
        self.assertEqual(row.source_kind, "document")
        self.assertEqual(row.chunk_index, 3)
        self.assertEqual(json.loads(row.metadata_json), {"untrusted": True})

    async def test_clear_messages_uses_conversation_scope(self):
        db = AsyncMock()
        repository = ChatRepository(db)

        await repository.clear_messages("conversation-1")

        db.execute.assert_awaited_once()
