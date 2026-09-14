import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.lib.generation_port import AiServiceGenerationPort, RagGenerationResult
from backend.modules.chat.infrastructure.streaming import encode_sse_event
from backend.modules.chat.schemas import ChatTokenEvent


def test_encode_sse_event_is_versioned_and_sequence_ordered(monkeypatch):
    monkeypatch.setattr(
        "backend.modules.chat.infrastructure.streaming.metrics.chat_stream_events_total",
        SimpleNamespace(labels=lambda **_: SimpleNamespace(inc=lambda: None)),
    )

    encoded = encode_sse_event(4, ChatTokenEvent(event="token", token="hello"))
    payload = json.loads(encoded.split("data: ", 1)[1])

    assert encoded.startswith("event: token\n")
    assert payload["contract_version"] == "v1"
    assert payload["sequence"] == 4
    assert payload["payload"] == {"event": "token", "token": "hello"}


class GenerationAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_bounded_stream_contract(self):
        adapter = AiServiceGenerationPort(SimpleNamespace())
        adapter.run_rag_answer = AsyncMock(
            return_value=RagGenerationResult(
                id="run-1",
                output_text="hello world",
                model_name="local",
            )
        )

        events = [
            event
            async for event in adapter.stream_rag_answer(
                SimpleNamespace(id="user-1"),
                query="hello",
                combined_context="",
                retrieved_chunk_ids=[],
            )
        ]

        self.assertEqual([event.text for event in events[:-1]], ["hello ", "world"])
        self.assertEqual(events[-1].result.id, "run-1")
