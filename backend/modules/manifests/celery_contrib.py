"""Celery contributions derived from active module manifests.

Task modules remain importable for eager/local tooling, but worker routes,
queues, and beat entries are filtered to the active capability profile.
"""

from __future__ import annotations

from typing import Any

from backend.core.config import settings
from backend.modules.manifests import get_manifest_map
from backend.modules.platform.profiles import ProfileResolution, resolve_active_modules

# Logical queue name (manifest celery_queues) → settings queue attribute / default.
_QUEUE_SETTING_ATTR: dict[str, str] = {
    "email": "CELERY_EMAIL_QUEUE",
    "ingestion": "CELERY_INGESTION_QUEUE",
    "cleanup": "CELERY_CLEANUP_QUEUE",
    "evaluation": "CELERY_EVALUATION_QUEUE",
    "memory": "CELERY_MEMORY_QUEUE",
    "ai": "CELERY_AI_QUEUE",
}

# Module key → task_name → logical queue name.
MODULE_TASK_ROUTES: dict[str, dict[str, str]] = {
    "rag": {
        "backend.workers.tasks.index_rag_document_task": "ingestion",
        "backend.workers.tasks.cleanup_rag_document_task": "cleanup",
        "backend.workers.tasks.cleanup_retired_rag_index_versions_task": "cleanup",
    },
    "chat": {
        "backend.workers.tasks.cleanup_chat_retention_task": "cleanup",
    },
    "ai": {
        "backend.workers.tasks.run_ai_evaluation_task": "evaluation",
        "backend.workers.tasks.run_ai_generation_task": "ai",
    },
    "memory": {
        "backend.workers.tasks.extract_turn_memories_task": "memory",
    },
    # <generic-app:task-routes>
    # </generic-app:task-routes>
}

# Scaffold-generated Celery task modules (filtered by active profile at worker boot).
GENERATED_TASK_MODULES: tuple[str, ...] = (
    # <generic-app:task-modules>
    # </generic-app:task-modules>
)

# Always-on platform task routes (identity/email/outbox), independent of packs.
CORE_TASK_ROUTES: dict[str, str] = {
    "backend.workers.tasks.send_email_task": "email",
}

# Module key → beat entry name → schedule definition (task + seconds).
MODULE_BEAT_ENTRIES: dict[str, dict[str, dict[str, Any]]] = {
    "chat": {
        "cleanup-expired-chat-conversations": {
            "task": "backend.workers.tasks.cleanup_chat_retention_task",
            "schedule": 3600.0,
        },
    },
    "rag": {
        "cleanup-retired-rag-index-versions": {
            "task": "backend.workers.tasks.cleanup_retired_rag_index_versions_task",
            "schedule": 3600.0,
        },
    },
}

CORE_BEAT_ENTRIES: dict[str, dict[str, Any]] = {
    "dispatch-background-job-outbox": {
        "task": "backend.workers.tasks.dispatch_outbox_task",
        "schedule": 30.0,
    },
    "cleanup-expired-idempotency-records": {
        "task": "backend.workers.tasks.cleanup_idempotency_records_task",
        "schedule": 900.0,
    },
}


def _queue_name(logical: str) -> str:
    attr = _QUEUE_SETTING_ATTR.get(logical)
    if attr is None:
        return logical
    return str(getattr(settings, attr, logical))


def build_celery_task_routes(
    active_modules: set[str] | frozenset[str] | tuple[str, ...],
) -> dict[str, dict[str, str]]:
    enabled = set(active_modules)
    routes: dict[str, dict[str, str]] = {}
    for task_name, logical_queue in CORE_TASK_ROUTES.items():
        routes[task_name] = {"queue": _queue_name(logical_queue)}
    for module_key, module_routes in MODULE_TASK_ROUTES.items():
        if module_key not in enabled:
            continue
        for task_name, logical_queue in module_routes.items():
            routes[task_name] = {"queue": _queue_name(logical_queue)}
    return routes


def build_celery_beat_schedule(
    active_modules: set[str] | frozenset[str] | tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    enabled = set(active_modules)
    schedule: dict[str, dict[str, Any]] = dict(CORE_BEAT_ENTRIES)
    for module_key, entries in MODULE_BEAT_ENTRIES.items():
        if module_key not in enabled:
            continue
        schedule.update(entries)
    return schedule


def active_celery_queues(
    active_modules: set[str] | frozenset[str] | tuple[str, ...],
) -> tuple[str, ...]:
    enabled = set(active_modules)
    queues: set[str] = set()
    by_key = get_manifest_map()
    for module_key in enabled:
        manifest = by_key.get(module_key)
        if manifest is None:
            continue
        queues.update(manifest.celery_queues)
    return tuple(sorted(queues))


def celery_include_modules(
    active_modules: set[str] | frozenset[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Celery ``include`` list: core tasks plus generated modules that are active."""

    includes = ["backend.workers.tasks"]
    if active_modules is None:
        includes.extend(GENERATED_TASK_MODULES)
        return includes
    enabled = set(active_modules)
    for dotted in GENERATED_TASK_MODULES:
        # backend.modules.<key>.workers
        parts = dotted.split(".")
        module_key = parts[2] if len(parts) >= 4 else dotted
        if module_key in enabled:
            includes.append(dotted)
    return includes


def celery_runtime_for_profile(
    profile: str | None = None,
    *,
    module_overrides: dict[str, bool] | None = None,
) -> tuple[ProfileResolution, dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    resolution = resolve_active_modules(profile, module_overrides=module_overrides)
    routes = build_celery_task_routes(resolution.active_modules)
    beat = build_celery_beat_schedule(resolution.active_modules)
    return resolution, routes, beat


__all__ = [
    "CORE_BEAT_ENTRIES",
    "CORE_TASK_ROUTES",
    "GENERATED_TASK_MODULES",
    "MODULE_BEAT_ENTRIES",
    "MODULE_TASK_ROUTES",
    "active_celery_queues",
    "build_celery_beat_schedule",
    "build_celery_task_routes",
    "celery_include_modules",
    "celery_runtime_for_profile",
]
