"""Capability profile matrix and runtime gating tests."""

from __future__ import annotations

import unittest

from backend.api.router_registry import active_router_keys, build_api_router
from backend.modules.manifests.celery_contrib import (
    build_celery_beat_schedule,
    build_celery_task_routes,
)
from backend.modules.platform.defaults import MODULE_PACKS
from backend.modules.platform.optional_manifests import OPTIONAL_PLATFORM_MANIFESTS
from backend.modules.platform.profiles import (
    CAPABILITY_PROFILES,
    CapabilityProfileError,
    optional_modules_for_profile,
    resolve_active_modules,
    resolve_capability_profile,
    selected_modules_for_profile,
    validate_capability_profiles,
)


class CapabilityProfileMatrixTest(unittest.TestCase):
    def test_profiles_validate_cleanly(self) -> None:
        validate_capability_profiles()

    def test_module_packs_derived_from_profiles(self) -> None:
        self.assertEqual(set(MODULE_PACKS), set(CAPABILITY_PROFILES))
        for key, pack in MODULE_PACKS.items():
            self.assertEqual(
                pack["modules"],
                list(optional_modules_for_profile(key)),
            )

    def test_required_profile_keys_exist(self) -> None:
        for key in (
            "core",
            "lean_saas",
            "rag",
            "agent",
            "automation_suite",
            "client_portal",
            "full_platform",
        ):
            self.assertIn(key, CAPABILITY_PROFILES)

    def test_core_has_no_optional_or_specialist_modules(self) -> None:
        resolution = resolve_capability_profile("core")
        self.assertEqual(resolution.optional_modules, ())
        self.assertEqual(resolution.selected_modules, ())
        self.assertIn("projects", resolution.active_modules)
        self.assertIn("identity_access", resolution.active_modules)
        self.assertNotIn("billing", resolution.active_modules)
        self.assertNotIn("rag", resolution.active_modules)
        self.assertNotIn("chat", resolution.active_modules)
        self.assertNotIn("ai", resolution.active_modules)
        self.assertNotIn("rag", resolution.backend_router_keys)
        self.assertNotIn("chat", resolution.backend_router_keys)

    def test_lean_saas_enables_billing(self) -> None:
        resolution = resolve_capability_profile("lean_saas")
        self.assertIn("billing", resolution.optional_modules)
        self.assertIn("billing", resolution.active_modules)
        self.assertIn("platform", resolution.backend_router_keys)
        self.assertNotIn("rag", resolution.active_modules)

    def test_rag_and_agent_include_ai_stack(self) -> None:
        rag = resolve_capability_profile("rag")
        agent = resolve_capability_profile("agent")
        for resolution in (rag, agent):
            self.assertIn("rag", resolution.active_modules)
            self.assertIn("ai", resolution.active_modules)
            self.assertIn("storage", resolution.active_modules)
            self.assertIn("ingestion", resolution.celery_queues)
        self.assertNotIn("chat", rag.active_modules)
        self.assertNotIn("memory", rag.active_modules)
        self.assertIn("chat", agent.active_modules)
        self.assertIn("memory", agent.active_modules)
        self.assertIn("memory", agent.celery_queues)

    def test_agent_extends_rag(self) -> None:
        self.assertEqual(CAPABILITY_PROFILES["agent"].extends, "rag")
        self.assertEqual(CAPABILITY_PROFILES["rag"].extends, "core")
        self.assertTrue(
            set(selected_modules_for_profile("rag")).issubset(
                set(selected_modules_for_profile("agent"))
            )
        )

    def test_full_platform_includes_all_optional(self) -> None:
        resolution = resolve_capability_profile("full_platform")
        optional_keys = {m.key for m in OPTIONAL_PLATFORM_MANIFESTS}
        self.assertEqual(set(resolution.optional_modules), optional_keys)
        self.assertTrue(optional_keys.issubset(set(resolution.active_modules)))
        self.assertIn("chat", resolution.active_modules)
        self.assertIn("developer_diagnostics", resolution.active_modules)

    def test_overrides_can_disable_optional_module(self) -> None:
        resolution = resolve_capability_profile(
            "full_platform",
            module_overrides={"billing": False},
        )
        self.assertNotIn("billing", resolution.optional_modules)
        self.assertNotIn("billing", resolution.active_modules)

    def test_unknown_profile_fails_clearly(self) -> None:
        with self.assertRaises(CapabilityProfileError) as ctx:
            resolve_capability_profile("not_a_real_profile")
        self.assertIn("Unknown capability profile", str(ctx.exception))

    def test_resolution_exposes_nav_and_routes(self) -> None:
        resolution = resolve_capability_profile("agent")
        paths = {entry["path"] for entry in resolution.nav_entries}
        self.assertIn("/projects", paths)
        self.assertIn("/knowledge-chat", paths)
        self.assertGreater(len(resolution.frontend_routes), 0)
        self.assertGreater(len(resolution.required_permissions), 0)

        core = resolve_capability_profile("core")
        core_paths = {entry["path"] for entry in core.nav_entries}
        self.assertNotIn("/knowledge-chat", core_paths)

    def test_no_runtime_install_surface(self) -> None:
        for key, profile in CAPABILITY_PROFILES.items():
            for module_key in optional_modules_for_profile(key):
                self.assertNotIn("==", module_key)
                self.assertNotIn("/", module_key)
            self.assertFalse(hasattr(profile, "pip_packages"))

    def test_resolve_active_modules_matches_capability_profile(self) -> None:
        for key in CAPABILITY_PROFILES:
            via_legacy = resolve_capability_profile(key)
            via_active = resolve_active_modules(key)
            self.assertEqual(via_legacy.active_modules, via_active.active_modules)
            self.assertEqual(via_legacy.backend_router_keys, via_active.backend_router_keys)


class ProfileRuntimeGatingTest(unittest.TestCase):
    def test_core_openapi_excludes_rag_and_chat(self) -> None:
        app_router = build_api_router(profile="core")
        paths = {route.path for route in app_router.routes}  # type: ignore[attr-defined]
        joined = " ".join(sorted(paths))
        self.assertNotIn("/rag", joined)
        self.assertNotIn("/chat", joined)
        self.assertNotIn("/memory", joined)
        self.assertIn("/projects", joined)
        self.assertIn("/auth", joined)

    def test_rag_openapi_includes_rag_excludes_chat(self) -> None:
        app_router = build_api_router(profile="rag")
        paths = " ".join(sorted({route.path for route in app_router.routes}))  # type: ignore[attr-defined]
        self.assertIn("/rag", paths)
        self.assertIn("/ai", paths)
        self.assertNotIn("/chat", paths)
        self.assertNotIn("/memory", paths)

    def test_agent_openapi_includes_chat_and_memory(self) -> None:
        app_router = build_api_router(profile="agent")
        paths = " ".join(sorted({route.path for route in app_router.routes}))  # type: ignore[attr-defined]
        self.assertIn("/rag", paths)
        self.assertIn("/chat", paths)
        self.assertIn("/memory", paths)

    def test_core_celery_omits_rag_and_chat_schedules(self) -> None:
        resolution = resolve_active_modules("core")
        routes = build_celery_task_routes(resolution.active_modules)
        beat = build_celery_beat_schedule(resolution.active_modules)
        self.assertNotIn("backend.workers.tasks.index_rag_document_task", routes)
        self.assertNotIn("backend.workers.tasks.cleanup_chat_retention_task", routes)
        self.assertNotIn("cleanup-expired-chat-conversations", beat)
        self.assertIn("dispatch-background-job-outbox", beat)
        self.assertNotIn("ingestion", resolution.celery_queues)

    def test_rag_celery_includes_ingestion_omits_chat_beat(self) -> None:
        resolution = resolve_active_modules("rag")
        routes = build_celery_task_routes(resolution.active_modules)
        beat = build_celery_beat_schedule(resolution.active_modules)
        self.assertIn("backend.workers.tasks.index_rag_document_task", routes)
        self.assertNotIn("cleanup-expired-chat-conversations", beat)
        self.assertIn("ingestion", resolution.celery_queues)

    def test_agent_celery_includes_chat_beat_and_memory_queue(self) -> None:
        resolution = resolve_active_modules("agent")
        routes = build_celery_task_routes(resolution.active_modules)
        beat = build_celery_beat_schedule(resolution.active_modules)
        self.assertIn("cleanup-expired-chat-conversations", beat)
        self.assertIn("backend.workers.tasks.extract_turn_memories_task", routes)
        self.assertIn("memory", resolution.celery_queues)

    def test_active_router_keys_follow_manifests(self) -> None:
        keys = active_router_keys(resolve_active_modules("core").active_modules)
        self.assertIn("projects", keys)
        self.assertNotIn("rag", keys)
        self.assertNotIn("chat", keys)

    def test_every_profile_open_api_and_celery_matrix(self) -> None:
        """Prompt 7.1: each named profile alters routers/queues/nav meaningfully."""

        specialist_path_tokens = ("/rag", "/chat", "/memory", "/ai", "/agent")
        summaries: dict[
            str, tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]
        ] = {}

        for key, profile in CAPABILITY_PROFILES.items():
            resolution = resolve_active_modules(key)
            router = build_api_router(profile=key)
            paths = " ".join(sorted({route.path for route in router.routes}))  # type: ignore[attr-defined]
            routes = build_celery_task_routes(resolution.active_modules)
            beat = build_celery_beat_schedule(resolution.active_modules)
            nav_paths = frozenset(
                str(entry["path"]) for entry in resolution.nav_entries if entry.get("path")
            )
            page_keys = frozenset(
                str(entry["page_key"])
                for entry in resolution.frontend_routes
                if entry.get("page_key")
            )

            for expected in profile.expected_router_keys:
                self.assertIn(
                    expected,
                    resolution.backend_router_keys,
                    f"{key} missing router {expected}",
                )
            for forbidden in profile.forbidden_router_keys:
                self.assertNotIn(
                    forbidden,
                    resolution.backend_router_keys,
                    f"{key} unexpectedly exposes {forbidden}",
                )
                self.assertNotIn(f"/{forbidden}", paths)

            for queue in profile.expected_celery_queues:
                self.assertIn(queue, resolution.celery_queues, f"{key} missing queue {queue}")

            self.assertTrue(resolution.health_checks, f"{key} should expose health checks")
            self.assertTrue(resolution.active_modules)
            self.assertTrue(nav_paths)
            self.assertIn("/projects", nav_paths)
            self.assertIn("dispatch-background-job-outbox", beat)

            if "rag" not in resolution.active_modules:
                for token in ("/rag", "/chat", "/memory"):
                    self.assertNotIn(token, paths)
                self.assertNotIn("ingestion", resolution.celery_queues)
            if "chat" in resolution.active_modules:
                self.assertIn("/chat", paths)
                self.assertIn("cleanup-expired-chat-conversations", beat)

            summaries[key] = (
                frozenset(resolution.active_modules),
                frozenset(resolution.optional_modules),
                frozenset(resolution.celery_queues),
                page_keys,
            )

            # Core-like profiles must not advertise specialist frontend pages.
            if key in {"core", "lean_saas", "automation_suite", "client_portal"}:
                for token in specialist_path_tokens:
                    self.assertNotIn(token, paths)
                self.assertFalse(any("knowledge-chat" in path for path in nav_paths))

            _ = routes  # routes built to ensure no raise for every profile

        # Profiles must not collapse into identical runtime matrices.
        self.assertNotEqual(summaries["core"], summaries["rag"])
        self.assertNotEqual(summaries["rag"], summaries["agent"])
        self.assertNotEqual(summaries["core"][1], summaries["lean_saas"][1])
        self.assertIn("billing", summaries["lean_saas"][1])
        self.assertNotEqual(summaries["lean_saas"][1], summaries["automation_suite"][1])
        self.assertIn("webhooks", summaries["automation_suite"][1])
        self.assertNotEqual(summaries["client_portal"], summaries["full_platform"])
        self.assertTrue(
            summaries["full_platform"][0].issuperset(summaries["agent"][0]),
            "full_platform should include agent modules",
        )

    def test_full_platform_includes_jobs_diagnostics_and_rag_ops(self) -> None:
        resolution = resolve_active_modules("full_platform")
        for key in ("jobs", "diagnostics", "rag", "chat", "developer_diagnostics"):
            self.assertIn(key, resolution.active_modules)
        self.assertIn("ingestion", resolution.celery_queues)
        self.assertIn("memory", resolution.celery_queues)
