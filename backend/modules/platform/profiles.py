"""Starter capability profiles built on module manifests.

Profiles are deterministic named slices of the platform (core, lean_saas, rag, …).
They select already-registered modules — no runtime package installation.

Semantics:
* ``always_enabled`` manifests → required core (always active)
* ``modules`` on a profile → profile-selected specialists (ai/rag/chat/…)
* ``optional_modules`` → SaaS pack toggles (billing/api_keys/…) overridable at runtime

``resolve_active_modules`` is the authoritative bootstrap resolver consumed by
API routers, Celery, and platform metadata / frontend allow-lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.config import settings
from backend.modules.manifests import (
    ModuleManifestError,
    effective_modules,
    frontend_routes_for_modules,
    get_manifest_map,
    nav_entries_for_modules,
)
from backend.modules.platform.optional_manifests import OPTIONAL_PLATFORM_MANIFESTS

ALL_OPTIONAL_MODULE_KEYS: tuple[str, ...] = tuple(
    manifest.key for manifest in OPTIONAL_PLATFORM_MANIFESTS
)

# Specialist stacks selected by profiles (not pack toggles, not required core).
RAG_STACK_MODULES: tuple[str, ...] = ("ai", "rag", "jobs", "diagnostics")
AGENT_STACK_MODULES: tuple[str, ...] = ("chat", "memory", "developer_diagnostics")
FULL_SPECIALIST_MODULES: tuple[str, ...] = RAG_STACK_MODULES + AGENT_STACK_MODULES

# Scaffold-generated modules appended to named profiles via ``--profile``.
PROFILE_EXTRA_MODULES: dict[str, tuple[str, ...]] = {
    # <generic-app:profile-extra-modules>
    # </generic-app:profile-extra-modules>
}


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Declarative starter profile (extends module packs, does not replace them)."""

    key: str
    label: str
    description: str
    optional_modules: tuple[str, ...] = ()
    #: Profile-selected modules (available specialists), inherited via ``extends``.
    modules: tuple[str, ...] = ()
    extends: str | None = None
    # Soft expectations checked against resolved manifests at startup/build.
    expected_router_keys: tuple[str, ...] = ()
    expected_celery_queues: tuple[str, ...] = ()
    recommended_feature_flags: tuple[str, ...] = ()
    #: Routers that must NOT appear for this profile (after resolution).
    forbidden_router_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileResolution:
    """Deterministic capability matrix for one profile (+ optional overrides)."""

    profile_key: str
    label: str
    description: str
    optional_modules: tuple[str, ...]
    selected_modules: tuple[str, ...]
    active_modules: tuple[str, ...]
    backend_router_keys: tuple[str, ...]
    celery_queues: tuple[str, ...]
    scheduled_tasks: tuple[str, ...]
    settings_prefixes: tuple[str, ...]
    health_checks: tuple[str, ...]
    required_permissions: tuple[str, ...]
    database_requirements: tuple[str, ...]
    feature_flags: tuple[str, ...]
    recommended_feature_flags: tuple[str, ...]
    nav_entries: tuple[dict[str, str | None], ...] = field(default_factory=tuple)
    frontend_routes: tuple[dict[str, str | None], ...] = field(default_factory=tuple)


def _profile_tuple() -> tuple[CapabilityProfile, ...]:
    return (
        CapabilityProfile(
            key="core",
            label="Core",
            description=(
                "Auth, users, profiles, projects, settings, and observability basics "
                "with no AI/RAG stack and no optional platform packs."
            ),
            optional_modules=(),
            modules=(),
            expected_router_keys=("projects", "profile", "settings"),
            forbidden_router_keys=("rag", "chat", "memory", "ai", "agent", "jobs"),
        ),
        CapabilityProfile(
            key="lean_saas",
            label="Lean SaaS",
            description="Core plus billing, API keys, and feature flags for a SaaS clone.",
            extends="core",
            optional_modules=("billing", "api_keys", "feature_flags"),
            expected_router_keys=("projects", "platform"),
            forbidden_router_keys=("rag", "chat", "memory"),
            recommended_feature_flags=("advanced_billing_controls",),
        ),
        CapabilityProfile(
            key="rag",
            label="RAG",
            description="Core plus AI providers, storage, document RAG, and ops consoles.",
            extends="core",
            optional_modules=(),
            modules=RAG_STACK_MODULES,
            expected_router_keys=("rag", "ai"),
            expected_celery_queues=("ingestion", "cleanup", "ai"),
            forbidden_router_keys=("chat", "memory"),
        ),
        CapabilityProfile(
            key="agent",
            label="Agent",
            description="RAG plus agent chat/runtime and memory workers.",
            extends="rag",
            optional_modules=(),
            modules=AGENT_STACK_MODULES,
            expected_router_keys=("rag", "ai", "chat", "memory"),
            expected_celery_queues=("ingestion", "memory", "ai"),
        ),
        CapabilityProfile(
            key="automation_suite",
            label="Automation Suite",
            description=(
                "Core plus API keys, webhooks, flags, and email templates for "
                "workflow-driven products."
            ),
            extends="core",
            optional_modules=(
                "api_keys",
                "webhooks",
                "feature_flags",
                "email_templates",
            ),
            expected_router_keys=("platform",),
            forbidden_router_keys=("rag", "chat", "memory"),
            recommended_feature_flags=("webhook_replay",),
        ),
        CapabilityProfile(
            key="client_portal",
            label="Client Portal",
            description="Subscription-led portal with flags and email customization.",
            extends="core",
            optional_modules=("billing", "feature_flags", "email_templates"),
            expected_router_keys=("projects", "platform"),
            forbidden_router_keys=("rag", "chat", "memory"),
        ),
        CapabilityProfile(
            key="full_platform",
            label="Full Platform",
            description="Every optional pack plus the full AI/RAG/agent specialist stack.",
            extends="core",
            optional_modules=ALL_OPTIONAL_MODULE_KEYS,
            modules=FULL_SPECIALIST_MODULES,
            expected_router_keys=("projects", "rag", "ai", "chat", "platform"),
            expected_celery_queues=("ingestion", "cleanup", "ai", "memory"),
        ),
    )


CAPABILITY_PROFILES: dict[str, CapabilityProfile] = {
    profile.key: profile for profile in _profile_tuple()
}


class CapabilityProfileError(RuntimeError):
    """Raised when capability profiles are inconsistent."""


def get_capability_profile(key: str) -> CapabilityProfile:
    try:
        return CAPABILITY_PROFILES[key]
    except KeyError as exc:
        known = ", ".join(sorted(CAPABILITY_PROFILES))
        raise CapabilityProfileError(
            f"Unknown capability profile {key!r}. Known profiles: {known}"
        ) from exc


def _walk_profile_field(profile_key: str, field_name: str) -> tuple[str, ...]:
    visiting: set[str] = set()

    def walk(key: str) -> list[str]:
        if key in visiting:
            raise CapabilityProfileError(
                f"Capability profile extends cycle involving {key!r}"
            )
        profile = get_capability_profile(key)
        visiting.add(key)
        values: list[str] = []
        if profile.extends is not None:
            values.extend(walk(profile.extends))
        values.extend(getattr(profile, field_name))
        visiting.remove(key)
        return values

    ordered: list[str] = []
    seen: set[str] = set()
    for module_key in walk(profile_key):
        if module_key not in seen:
            seen.add(module_key)
            ordered.append(module_key)
    return tuple(ordered)


def optional_modules_for_profile(profile_key: str) -> tuple[str, ...]:
    """Resolve optional pack modules including inherited ``extends`` parents."""

    return _walk_profile_field(profile_key, "optional_modules")


def selected_modules_for_profile(profile_key: str) -> tuple[str, ...]:
    """Resolve profile-selected specialist modules including ``extends`` parents."""

    base = _walk_profile_field(profile_key, "modules")
    extras: list[str] = []
    seen = set(base)
    # Walk extends chain so child profiles inherit scaffold extras from parents.
    visiting: set[str] = set()

    def walk_extras(key: str) -> None:
        if key in visiting:
            return
        visiting.add(key)
        profile = get_capability_profile(key)
        if profile.extends is not None:
            walk_extras(profile.extends)
        for module_key in PROFILE_EXTRA_MODULES.get(key, ()):
            if module_key not in seen:
                seen.add(module_key)
                extras.append(module_key)
        visiting.remove(key)

    walk_extras(profile_key)
    return tuple([*base, *extras])


def module_packs_from_profiles() -> dict[str, dict[str, object]]:
    """Shape compatible with legacy MODULE_PACKS entries (optional toggles only)."""

    packs: dict[str, dict[str, object]] = {}
    for key, profile in CAPABILITY_PROFILES.items():
        packs[key] = {
            "label": profile.label,
            "description": profile.description,
            "modules": list(optional_modules_for_profile(key)),
        }
    return packs


def _sorted_unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def resolve_capability_profile(
    profile_key: str,
    *,
    module_overrides: dict[str, bool] | None = None,
) -> ProfileResolution:
    """Compute the capability matrix for a profile (deterministic, no installs)."""

    profile = get_capability_profile(profile_key)
    optional = set(optional_modules_for_profile(profile_key))
    selected = set(selected_modules_for_profile(profile_key))
    if module_overrides:
        catalog_keys = {item.key for item in OPTIONAL_PLATFORM_MANIFESTS}
        known_manifests = set(get_manifest_map())
        for key, enabled in module_overrides.items():
            if key not in known_manifests:
                raise CapabilityProfileError(f"Unknown module override key: {key}")
            if key in catalog_keys:
                if enabled:
                    optional.add(key)
                else:
                    optional.discard(key)
                continue
            # Allow explicit enable/disable of profile-selected specialists via overrides.
            if enabled:
                selected.add(key)
            else:
                selected.discard(key)

    try:
        active = effective_modules(optional, enabled_selected=selected)
    except ModuleManifestError as exc:
        raise CapabilityProfileError(str(exc)) from exc

    router_keys: list[str] = []
    queues: list[str] = []
    scheduled: list[str] = []
    settings_prefixes: list[str] = []
    health_checks: list[str] = []
    permissions: list[str] = []
    database_requirements: list[str] = []
    feature_flags: list[str] = []

    by_key = get_manifest_map()
    for key in sorted(active):
        manifest = by_key[key]
        router_keys.extend(manifest.backend_router_keys)
        queues.extend(manifest.celery_queues)
        scheduled.extend(manifest.scheduled_tasks)
        settings_prefixes.extend(manifest.settings_prefixes)
        health_checks.extend(manifest.health_checks)
        permissions.extend(manifest.required_permissions)
        database_requirements.extend(manifest.database_requirements)
        feature_flags.extend(manifest.feature_flags)

    return ProfileResolution(
        profile_key=profile.key,
        label=profile.label,
        description=profile.description,
        optional_modules=tuple(sorted(optional)),
        selected_modules=tuple(sorted(selected)),
        active_modules=tuple(sorted(active)),
        backend_router_keys=_sorted_unique(router_keys),
        celery_queues=_sorted_unique(queues),
        scheduled_tasks=_sorted_unique(scheduled),
        settings_prefixes=_sorted_unique(settings_prefixes),
        health_checks=_sorted_unique(health_checks),
        required_permissions=_sorted_unique(permissions),
        database_requirements=_sorted_unique(database_requirements),
        feature_flags=_sorted_unique(feature_flags),
        recommended_feature_flags=profile.recommended_feature_flags,
        nav_entries=tuple(nav_entries_for_modules(active)),
        frontend_routes=tuple(frontend_routes_for_modules(active)),
    )


def resolve_active_modules(
    profile: str | None = None,
    *,
    module_overrides: dict[str, bool] | None = None,
) -> ProfileResolution:
    """Authoritative runtime capability resolution for bootstrap consumers."""

    profile_key = profile or settings.capability_profile
    return resolve_capability_profile(profile_key, module_overrides=module_overrides)


def validate_capability_profiles() -> None:
    """Fail startup/build when any profile cannot resolve or expectations fail."""

    if not CAPABILITY_PROFILES:
        raise CapabilityProfileError("No capability profiles registered")

    known_optional = set(ALL_OPTIONAL_MODULE_KEYS)
    known_manifests = set(get_manifest_map())

    for key in CAPABILITY_PROFILES:
        profile = CAPABILITY_PROFILES[key]
        if profile.extends is not None and profile.extends not in CAPABILITY_PROFILES:
            raise CapabilityProfileError(
                f"Profile {key!r} extends unknown profile {profile.extends!r}"
            )
        optional = optional_modules_for_profile(key)
        unknown_optional = set(optional) - known_optional
        stray = unknown_optional - known_manifests
        if stray:
            raise CapabilityProfileError(
                f"Profile {key!r} references unknown modules: {sorted(stray)}"
            )
        non_optional = unknown_optional & known_manifests
        if non_optional:
            raise CapabilityProfileError(
                f"Profile {key!r} lists always-on/selected modules as optional: "
                f"{sorted(non_optional)}"
            )

        selected = selected_modules_for_profile(key)
        unknown_selected = set(selected) - known_manifests
        if unknown_selected:
            raise CapabilityProfileError(
                f"Profile {key!r} selects unknown modules: {sorted(unknown_selected)}"
            )
        optional_as_selected = set(selected) & known_optional
        if optional_as_selected:
            raise CapabilityProfileError(
                f"Profile {key!r} lists optional pack modules under modules=; "
                f"use optional_modules instead: {sorted(optional_as_selected)}"
            )

        resolution = resolve_capability_profile(key)
        missing_routers = set(profile.expected_router_keys) - set(
            resolution.backend_router_keys
        )
        if missing_routers:
            raise CapabilityProfileError(
                f"Profile {key!r} missing expected routers: {sorted(missing_routers)}"
            )
        forbidden = set(profile.forbidden_router_keys) & set(
            resolution.backend_router_keys
        )
        if forbidden:
            raise CapabilityProfileError(
                f"Profile {key!r} unexpectedly exposes routers: {sorted(forbidden)}"
            )
        missing_queues = set(profile.expected_celery_queues) - set(
            resolution.celery_queues
        )
        if missing_queues:
            raise CapabilityProfileError(
                f"Profile {key!r} missing expected celery queues: "
                f"{sorted(missing_queues)}"
            )


def profile_resolution_payload(resolution: ProfileResolution) -> dict[str, object]:
    """JSON-friendly summary for platform metadata/config."""

    return {
        "key": resolution.profile_key,
        "label": resolution.label,
        "description": resolution.description,
        "optional_modules": list(resolution.optional_modules),
        "selected_modules": list(resolution.selected_modules),
        "active_modules": list(resolution.active_modules),
        "backend_router_keys": list(resolution.backend_router_keys),
        "celery_queues": list(resolution.celery_queues),
        "scheduled_tasks": list(resolution.scheduled_tasks),
        "settings_prefixes": list(resolution.settings_prefixes),
        "health_checks": list(resolution.health_checks),
        "required_permissions": list(resolution.required_permissions),
        "database_requirements": list(resolution.database_requirements),
        "feature_flags": list(resolution.feature_flags),
        "recommended_feature_flags": list(resolution.recommended_feature_flags),
        "nav_entry_count": len(resolution.nav_entries),
        "frontend_route_count": len(resolution.frontend_routes),
    }


__all__ = [
    "ALL_OPTIONAL_MODULE_KEYS",
    "AGENT_STACK_MODULES",
    "CAPABILITY_PROFILES",
    "FULL_SPECIALIST_MODULES",
    "RAG_STACK_MODULES",
    "CapabilityProfile",
    "CapabilityProfileError",
    "ProfileResolution",
    "get_capability_profile",
    "module_packs_from_profiles",
    "optional_modules_for_profile",
    "profile_resolution_payload",
    "resolve_active_modules",
    "resolve_capability_profile",
    "selected_modules_for_profile",
    "validate_capability_profiles",
    "PROFILE_EXTRA_MODULES",
]
