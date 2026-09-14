"""Starter capability profiles built on module manifests.

Profiles are deterministic named slices of the platform (core, lean_saas, rag, …).
They extend the existing module-pack concept: each profile's optional module list
is what `MODULE_PACKS` exposes, and resolution aggregates routers, queues, nav,
routes, settings, and permissions from effective manifests.

No runtime package installation — profiles only select already-registered modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Declarative starter profile (extends module packs, does not replace them)."""

    key: str
    label: str
    description: str
    optional_modules: tuple[str, ...] = ()
    extends: str | None = None
    # Soft expectations checked against resolved manifests at startup/build.
    expected_router_keys: tuple[str, ...] = ()
    expected_celery_queues: tuple[str, ...] = ()
    recommended_feature_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileResolution:
    """Deterministic capability matrix for one profile (+ optional overrides)."""

    profile_key: str
    label: str
    description: str
    optional_modules: tuple[str, ...]
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
                "with no optional platform packs."
            ),
            optional_modules=(),
            expected_router_keys=("projects", "profile", "settings"),
        ),
        CapabilityProfile(
            key="lean_saas",
            label="Lean SaaS",
            description="Core plus billing, API keys, and feature flags for a SaaS clone.",
            extends="core",
            optional_modules=("billing", "api_keys", "feature_flags"),
            expected_router_keys=("projects", "platform"),
            recommended_feature_flags=("advanced_billing_controls",),
        ),
        CapabilityProfile(
            key="rag",
            label="RAG",
            description=(
                "Core plus AI providers, storage, and document RAG "
                "(always-on AI/RAG stack)."
            ),
            extends="core",
            optional_modules=(),
            expected_router_keys=("rag", "ai"),
            expected_celery_queues=("ingestion", "cleanup", "ai"),
        ),
        CapabilityProfile(
            key="agent",
            label="Agent",
            description="RAG plus agent chat/runtime and memory workers where present.",
            extends="rag",
            optional_modules=(),
            expected_router_keys=("rag", "ai", "chat"),
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
            recommended_feature_flags=("webhook_replay",),
        ),
        CapabilityProfile(
            key="client_portal",
            label="Client Portal",
            description="Subscription-led portal with flags and email customization.",
            extends="core",
            optional_modules=("billing", "feature_flags", "email_templates"),
            expected_router_keys=("projects", "platform"),
        ),
        CapabilityProfile(
            key="full_platform",
            label="Full Platform",
            description="Enable every optional platform module on top of core.",
            extends="core",
            optional_modules=ALL_OPTIONAL_MODULE_KEYS,
            expected_router_keys=("projects", "rag", "ai", "platform"),
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


def optional_modules_for_profile(profile_key: str) -> tuple[str, ...]:
    """Resolve optional modules including inherited `extends` parents."""

    visiting: set[str] = set()

    def walk(key: str) -> list[str]:
        if key in visiting:
            raise CapabilityProfileError(
                f"Capability profile extends cycle involving {key!r}"
            )
        profile = get_capability_profile(key)
        visiting.add(key)
        modules: list[str] = []
        if profile.extends is not None:
            modules.extend(walk(profile.extends))
        modules.extend(profile.optional_modules)
        visiting.remove(key)
        return modules

    ordered: list[str] = []
    seen: set[str] = set()
    for module_key in walk(profile_key):
        if module_key not in seen:
            seen.add(module_key)
            ordered.append(module_key)
    return tuple(ordered)


def module_packs_from_profiles() -> dict[str, dict[str, object]]:
    """Shape compatible with legacy MODULE_PACKS entries."""

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
    if module_overrides:
        catalog_keys = {item.key for item in OPTIONAL_PLATFORM_MANIFESTS}
        for key, enabled in module_overrides.items():
            if key not in catalog_keys and key not in get_manifest_map():
                raise CapabilityProfileError(f"Unknown module override key: {key}")
            if key not in catalog_keys:
                # Always-on keys in overrides are ignored (pack compatibility).
                continue
            if enabled:
                optional.add(key)
            else:
                optional.discard(key)

    try:
        active = effective_modules(optional)
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
        unknown = set(optional) - known_optional
        # Allow documenting always-on modules in optional_modules for clarity, but
        # packs should only list optional catalog keys.
        stray = unknown - known_manifests
        if stray:
            raise CapabilityProfileError(
                f"Profile {key!r} references unknown modules: {sorted(stray)}"
            )
        non_optional = unknown & known_manifests
        if non_optional:
            raise CapabilityProfileError(
                f"Profile {key!r} lists always-on modules as optional: "
                f"{sorted(non_optional)}"
            )

        resolution = resolve_capability_profile(key)
        missing_routers = set(profile.expected_router_keys) - set(
            resolution.backend_router_keys
        )
        if missing_routers:
            raise CapabilityProfileError(
                f"Profile {key!r} missing expected routers: {sorted(missing_routers)}"
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
    "CAPABILITY_PROFILES",
    "CapabilityProfile",
    "CapabilityProfileError",
    "ProfileResolution",
    "get_capability_profile",
    "module_packs_from_profiles",
    "optional_modules_for_profile",
    "profile_resolution_payload",
    "resolve_capability_profile",
    "validate_capability_profiles",
]
