from __future__ import annotations

import json

from backend.modules.chat import metrics
from backend.modules.chat.schemas import ChatEventEnvelope, ChatStreamEvent


def encode_sse_event(sequence: int, payload: ChatStreamEvent) -> str:
    """Encode one versioned chat event and record its bounded event metric."""

    metrics.chat_stream_events_total.labels(event=payload.event).inc()
    envelope = ChatEventEnvelope(sequence=sequence, payload=payload)
    return f"event: {payload.event}\ndata: {json.dumps(envelope.model_dump(mode='json'))}\n\n"
