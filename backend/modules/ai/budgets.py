from __future__ import annotations

from fastapi import HTTPException

from backend.core.config import settings


def utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def validate_prompt_budget(system_prompt: str, user_prompt: str) -> None:
    prompt_bytes = utf8_size(system_prompt) + utf8_size(user_prompt)
    if prompt_bytes > settings.AI_MAX_PROMPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The generated prompt exceeds the configured size limit.",
        )


def validate_context_budget(context: str) -> None:
    if utf8_size(context) > settings.AI_MAX_CONTEXT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Retrieved context exceeds the configured size limit.",
        )
