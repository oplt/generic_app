import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError

from backend.core.config import Settings
from backend.lib.project_access import SqlAlchemyProjectAccessPort
from backend.modules.chat.schemas import (
    ChatErrorEvent,
    ChatEventEnvelope,
    ChatMessageRequest,
)


def settings_payload(**overrides):
    payload = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/app",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "a" * 64,
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
    }
    payload.update(overrides)
    return payload


class Phase0SettingsTest(unittest.TestCase):
    def test_chat_and_web_search_are_disabled_by_default(self):
        config = Settings.model_validate(settings_payload())

        self.assertFalse(config.CHAT_ENABLED)
        self.assertFalse(config.WEB_SEARCH_ENABLED)
        self.assertEqual(config.CHAT_DEFAULT_MODE, "auto")

    def test_enabled_web_search_requires_provider_credentials(self):
        with self.assertRaises(ValueError):
            Settings.model_validate(settings_payload(WEB_SEARCH_ENABLED=True))

    def test_web_default_mode_requires_enabled_search(self):
        with self.assertRaises(ValueError):
            Settings.model_validate(settings_payload(CHAT_DEFAULT_MODE="web"))


class Phase0OwnershipTest(unittest.IsolatedAsyncioTestCase):
    async def test_scope_is_server_derived_for_an_authorized_project(self):
        port = SqlAlchemyProjectAccessPort(AsyncMock())
        port._repo.get_by_id_for_user = AsyncMock(
            return_value=SimpleNamespace(id="project-1", owner_id="user-1")
        )
        port._identity_repo.get_default_organization_id = AsyncMock(return_value="org-1")

        scope = await port.resolve_ownership_scope("user-1", "project-1")

        self.assertEqual(scope.user_id, "user-1")
        self.assertEqual(scope.project_id, "project-1")
        self.assertEqual(scope.organization_id, "org-1")

    async def test_scope_rejects_a_project_not_authorized_for_user(self):
        port = SqlAlchemyProjectAccessPort(AsyncMock())
        port._repo.get_by_id_for_user = AsyncMock(return_value=None)
        port._identity_repo.get_default_organization_id = AsyncMock(return_value="org-1")

        with self.assertRaises(HTTPException) as raised:
            await port.resolve_ownership_scope("user-1", "project-2")

        self.assertEqual(raised.exception.status_code, 403)


class Phase0ChatContractTest(unittest.TestCase):
    def test_client_contract_does_not_accept_ownership_claims(self):
        request = ChatMessageRequest(
            content="Summarize the selected document",
            project_id="project-1",
            document_ids=["document-1"],
        )

        self.assertNotIn("user_id", request.model_dump())
        self.assertNotIn("organization_id", request.model_dump())

    def test_stream_events_are_discriminated_and_errors_are_safe(self):
        event = ChatEventEnvelope.model_validate(
            {
                "sequence": 1,
                "payload": {
                    "event": "error",
                    "code": "provider_timeout",
                    "message": "The AI provider timed out.",
                    "retryable": True,
                },
            }
        )

        self.assertIsInstance(event.payload, ChatErrorEvent)
        self.assertEqual(event.contract_version, "v1")
        self.assertNotIn("prompt", event.payload.model_dump())

    def test_invalid_chat_mode_is_rejected(self):
        with self.assertRaises(ValidationError):
            ChatMessageRequest(content="hello", mode="unsupported")

    def test_documented_memory_controls_are_accepted(self):
        request = ChatMessageRequest(
            content="Use saved context",
            mode="general",
            memory_enabled=False,
            memory_write_enabled=False,
        )

        self.assertFalse(request.memory_enabled)
        self.assertFalse(request.memory_write_enabled)
