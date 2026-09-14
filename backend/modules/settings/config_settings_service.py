"""Env-backed configuration settings use case."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException

from backend.core.cache import (
    SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
    cache_bump_generation,
    cache_get_generation,
    cache_get_or_load_json,
    cache_key,
    get_local_cached_json,
    invalidate_settings_config_cache,
    set_local_cached_json,
)
from backend.core.config import ENV_FILE, Settings, settings
from backend.modules.settings.config_catalog import (
    CONFIG_FIELD_METADATA,
    CONFIG_NOTICE,
    DEPLOYMENT_MANAGED_CONFIG_KEYS,
    DEPRECATED_CONFIG_KEY_REPLACEMENTS,
    REDACTED_SECRET,
    SENSITIVE_KEY_MARKERS,
    TYPE_LABELS,
)
from backend.modules.settings.env_file_store import EnvFileStore
from backend.modules.settings.schemas import (
    ConfigEntryResponse,
    ConfigEntryUpdate,
    ConfigSettingsResponse,
)

logger = logging.getLogger(__name__)


class ConfigSettingsService:
    @classmethod
    async def list_config_entries(cls) -> ConfigSettingsResponse:
        generation = await cache_get_generation("settings-config")
        local_payload = get_local_cached_json(SETTINGS_CONFIG_ENTRIES_CACHE_KEY)
        if (
            isinstance(local_payload, dict)
            and local_payload.get("generation") == generation
            and isinstance(local_payload.get("response"), dict)
        ):
            return ConfigSettingsResponse.model_validate(local_payload["response"])
        cached = await cache_get_or_load_json(
            cache_key("settings", "config_entries", str(generation)),
            ttl_seconds=settings.CACHE_SETTINGS_TTL_SECONDS,
            loader=lambda: asyncio.to_thread(
                lambda: cls._build_config_entries().model_dump(mode="json")
            ),
        )
        set_local_cached_json(
            SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
            {"generation": generation, "response": cached},
            ttl_seconds=settings.CACHE_SETTINGS_TTL_SECONDS,
        )
        return ConfigSettingsResponse.model_validate(cached)

    @classmethod
    def _build_config_entries(cls) -> ConfigSettingsResponse:
        env_entries = {
            key: value
            for key, value in cls._read_env_entries().items()
            if key not in DEPRECATED_CONFIG_KEY_REPLACEMENTS
        }
        items: list[ConfigEntryResponse] = []
        known_fields = Settings.model_fields
        ordered_keys = list(env_entries)

        for key in known_fields:
            if key not in env_entries:
                ordered_keys.append(key)

        for key in ordered_keys:
            if key in env_entries:
                value = env_entries[key]
            elif key in known_fields:
                value = cls._serialize_value(getattr(settings, key))
            else:
                value = ""

            items.append(
                ConfigEntryResponse(
                    key=key,
                    value=REDACTED_SECRET if cls._is_secret_key(key) and value else value,
                    value_type=cls._get_value_type(key),
                    description=CONFIG_FIELD_METADATA.get(key, {}).get("description"),
                    requires_restart=CONFIG_FIELD_METADATA.get(key, {}).get(
                        "requires_restart", True
                    ),
                    is_custom=key not in known_fields,
                    is_secret=cls._is_secret_key(key),
                )
            )

        return ConfigSettingsResponse(items=items, notice=CONFIG_NOTICE)

    @classmethod
    def _update_config_entries_sync(
        cls, updates: Iterable[ConfigEntryUpdate]
    ) -> ConfigSettingsResponse:
        update_items = list(updates)
        seen_keys: set[str] = set()
        raw_updates: dict[str, str] = {}

        for item in update_items:
            key = item.key
            replacement = DEPRECATED_CONFIG_KEY_REPLACEMENTS.get(key)
            if replacement:
                raise HTTPException(
                    status_code=422,
                    detail=f"Config key {key} is deprecated; use {replacement}",
                )
            if key in seen_keys:
                raise HTTPException(status_code=400, detail=f"Duplicate config key: {key}")
            seen_keys.add(key)
            raw_updates[key] = item.value

        merged_known_values = {key: getattr(settings, key) for key in Settings.model_fields}
        for key, value in raw_updates.items():
            if cls._is_secret_key(key) and value == REDACTED_SECRET:
                value = cls._read_env_entries().get(
                    key, cls._serialize_value(getattr(settings, key, ""))
                )
                raw_updates[key] = value
            if key in merged_known_values:
                merged_known_values[key] = value

        try:
            validated = Settings.model_validate(merged_known_values)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        normalized_updates = raw_updates.copy()
        for key in Settings.model_fields:
            if key in normalized_updates:
                normalized_updates[key] = cls._serialize_value(getattr(validated, key))

        EnvFileStore(ENV_FILE).update(normalized_updates, parse_line=cls._parse_env_line)

        for key in Settings.model_fields:
            setattr(settings, key, getattr(validated, key))

        invalidate_settings_config_cache()
        logger.info("Environment config updated keys=%s", sorted(normalized_updates))
        return cls._build_config_entries()

    @classmethod
    async def update_config_entries(
        cls, updates: Iterable[ConfigEntryUpdate]
    ) -> ConfigSettingsResponse:
        update_items = list(updates)
        managed = DEPLOYMENT_MANAGED_CONFIG_KEYS.intersection(item.key for item in update_items)
        if settings.is_production and managed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Infrastructure and secret settings are deployment-managed in production: "
                    + ", ".join(sorted(managed))
                ),
            )
        response = await asyncio.to_thread(cls._update_config_entries_sync, update_items)
        await cache_bump_generation("settings-config")
        return response

    @staticmethod
    def _get_value_type(key: str) -> str:
        field = Settings.model_fields.get(key)
        if not field:
            return "string"
        return TYPE_LABELS.get(field.annotation, "string")

    @staticmethod
    def _serialize_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        normalized = key.upper()
        return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)

    @staticmethod
    def _parse_env_line(line: str) -> tuple[str, str] | None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            return None

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            return None
        return key, value.strip()

    @classmethod
    def _read_env_entries(cls) -> dict[str, str]:
        if not ENV_FILE.exists():
            return {}

        entries: dict[str, str] = {}
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            parsed = cls._parse_env_line(line)
            if parsed:
                key, value = parsed
                entries[key] = value
        return entries
