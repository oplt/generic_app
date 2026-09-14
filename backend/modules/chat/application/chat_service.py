"""Public application service boundary for knowledge chat."""

from backend.modules.chat.service import DocumentChatService


class ChatService(DocumentChatService):
    """Application-facing chat orchestrator.

    The inherited implementation keeps the historical import stable while
    exposing the application boundary used by routes and future adapters.
    """


__all__ = ["ChatService", "DocumentChatService"]
