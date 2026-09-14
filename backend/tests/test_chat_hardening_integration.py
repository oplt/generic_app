import unittest
from unittest.mock import patch

from backend.tests.integration_support import (
    api_client,
    auth_request,
    integration_enabled,
    rag_integration_ready,
    register_and_sign_in,
)


@unittest.skipUnless(
    integration_enabled() and rag_integration_ready(),
    "Set RUN_INTEGRATION_TESTS=1 and migrate postgres (alembic upgrade head)",
)
class ChatHardeningIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_conversation_isolation_clear_and_delete_journey(self):
        with patch("backend.modules.chat.api.settings.CHAT_ENABLED", True):
            async with api_client() as owner_client:
                await register_and_sign_in(owner_client)
                created = await auth_request(
                    owner_client,
                    "POST",
                    "/api/v1/chat/conversations",
                    json={"title": "Hardening journey", "mode": "general"},
                )
                self.assertEqual(created.status_code, 201, created.text)
                conversation_id = created.json()["id"]

                streamed = await auth_request(
                    owner_client,
                    "POST",
                    f"/api/v1/chat/conversations/{conversation_id}/messages/stream",
                    json={"content": "Say hello", "mode": "general"},
                )
                self.assertEqual(streamed.status_code, 200, streamed.text)

                populated = await owner_client.get(
                    f"/api/v1/chat/conversations/{conversation_id}"
                )
                self.assertEqual(len(populated.json()["messages"]), 2)

                async with api_client() as other_client:
                    await register_and_sign_in(other_client)
                    foreign = await other_client.get(
                        f"/api/v1/chat/conversations/{conversation_id}"
                    )
                    self.assertEqual(foreign.status_code, 404)
                    foreign_clear = await auth_request(
                        other_client,
                        "POST",
                        f"/api/v1/chat/conversations/{conversation_id}/clear",
                    )
                    self.assertEqual(foreign_clear.status_code, 404)

                cleared = await auth_request(
                    owner_client,
                    "POST",
                    f"/api/v1/chat/conversations/{conversation_id}/clear",
                )
                self.assertEqual(cleared.status_code, 204)
                empty = await owner_client.get(
                    f"/api/v1/chat/conversations/{conversation_id}"
                )
                self.assertEqual(empty.status_code, 200)
                self.assertEqual(empty.json()["messages"], [])

                deleted = await auth_request(
                    owner_client,
                    "DELETE",
                    f"/api/v1/chat/conversations/{conversation_id}",
                )
                self.assertEqual(deleted.status_code, 204)
                missing = await owner_client.get(
                    f"/api/v1/chat/conversations/{conversation_id}"
                )
                self.assertEqual(missing.status_code, 404)
