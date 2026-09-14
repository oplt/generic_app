from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backend.core.cache import cache_delete, cache_get_or_load_json, cache_key
from backend.core.config import settings
from backend.core.pagination import MAX_PAGE_LIMIT
from backend.modules.identity_access.models import User


def template_resolution_key(user_id: str, template_key: str) -> str:
    return cache_key("ai", "prompt-resolution", user_id, template_key)


def version_resolution_key(user_id: str, version_id: str) -> str:
    return cache_key("ai", "prompt-version", user_id, version_id)


def _version_payload(version: Any) -> dict[str, Any]:
    return {
        "id": version.id,
        "prompt_template_id": getattr(version, "prompt_template_id", None),
        "provider_key": getattr(version, "provider_key", "local"),
        "model_name": getattr(version, "model_name", settings.AI_LOCAL_MODEL_NAME),
        "system_prompt": getattr(version, "system_prompt", ""),
        "user_prompt_template": getattr(version, "user_prompt_template", ""),
        "variable_definitions_json": getattr(version, "variable_definitions_json", []),
        "response_format": getattr(version, "response_format", "text"),
        "temperature": getattr(version, "temperature", 0.2),
        "input_cost_per_million": getattr(version, "input_cost_per_million", 0),
        "output_cost_per_million": getattr(version, "output_cost_per_million", 0),
        "is_published": getattr(version, "is_published", False),
    }


def _resolved_models(payload: dict[str, Any]) -> tuple[Any, Any]:
    return (
        SimpleNamespace(**payload["template"]),
        SimpleNamespace(**payload["version"]),
    )


async def resolve_prompt(
    repo,
    user: User,
    *,
    template_key: str | None = None,
    version_id: str | None = None,
) -> tuple[Any, Any] | None:
    if version_id:
        key = version_resolution_key(user.id, version_id)

        async def load_version() -> dict[str, Any] | None:
            version = await repo.get_prompt_version(version_id)
            if not version:
                return None
            template = await repo.get_prompt_template_for_user(user.id, version.prompt_template_id)
            if not template:
                return None
            return {
                "template": {"id": template.id, "key": getattr(template, "key", template_key)},
                "version": _version_payload(version),
            }

    elif template_key:
        key = template_resolution_key(user.id, template_key)

        async def load_version() -> dict[str, Any] | None:
            template = await repo.get_prompt_template_by_key_for_user(user.id, template_key)
            if not template:
                return None
            versions, _ = await repo.list_prompt_versions(
                template.id, limit=MAX_PAGE_LIMIT, offset=0
            )
            version = None
            if template.active_version_id:
                version = next(
                    (item for item in versions if item.id == template.active_version_id), None
                )
            if version is None:
                version = next((item for item in versions if item.is_published), None)
            if version is None and versions:
                version = versions[0]
            if version is None:
                return None
            return {
                "template": {
                    "id": template.id,
                    "key": getattr(template, "key", template_key),
                },
                "version": _version_payload(version),
            }

    else:
        return None

    payload = await cache_get_or_load_json(
        key,
        ttl_seconds=settings.CACHE_PROMPT_RESOLUTION_TTL_SECONDS,
        loader=load_version,
    )
    return _resolved_models(payload) if payload else None


async def invalidate_prompt_resolution_cache(
    user_id: str,
    *,
    template_key: str | None = None,
    version_id: str | None = None,
) -> None:
    keys = []
    if template_key:
        keys.append(template_resolution_key(user_id, template_key))
    if version_id:
        keys.append(version_resolution_key(user_id, version_id))
    if keys:
        await cache_delete(*keys)
