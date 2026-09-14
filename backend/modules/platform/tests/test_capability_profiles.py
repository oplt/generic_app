"""Capability profile matrix and validation tests."""

from __future__ import annotations

import unittest

from backend.modules.platform.defaults import MODULE_PACKS
from backend.modules.platform.optional_manifests import OPTIONAL_PLATFORM_MANIFESTS
from backend.modules.platform.profiles import (
    CAPABILITY_PROFILES,
    CapabilityProfileError,
    optional_modules_for_profile,
    resolve_capability_profile,
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

    def test_core_has_no_optional_modules(self) -> None:
        resolution = resolve_capability_profile("core")
        self.assertEqual(resolution.optional_modules, ())
        self.assertIn("projects", resolution.active_modules)
        self.assertIn("identity_access", resolution.active_modules)
        self.assertNotIn("billing", resolution.active_modules)

    def test_lean_saas_enables_billing(self) -> None:
        resolution = resolve_capability_profile("lean_saas")
        self.assertIn("billing", resolution.optional_modules)
        self.assertIn("billing", resolution.active_modules)
        self.assertIn("platform", resolution.backend_router_keys)

    def test_rag_and_agent_include_ai_stack(self) -> None:
        rag = resolve_capability_profile("rag")
        agent = resolve_capability_profile("agent")
        for resolution in (rag, agent):
            self.assertIn("rag", resolution.active_modules)
            self.assertIn("ai", resolution.active_modules)
            self.assertIn("storage", resolution.active_modules)
            self.assertIn("ingestion", resolution.celery_queues)
        self.assertIn("chat", agent.active_modules)
        self.assertIn("memory", agent.active_modules)
        self.assertIn("memory", agent.celery_queues)

    def test_agent_extends_rag(self) -> None:
        self.assertEqual(CAPABILITY_PROFILES["agent"].extends, "rag")
        self.assertEqual(CAPABILITY_PROFILES["rag"].extends, "core")

    def test_full_platform_includes_all_optional(self) -> None:
        resolution = resolve_capability_profile("full_platform")
        optional_keys = {m.key for m in OPTIONAL_PLATFORM_MANIFESTS}
        self.assertEqual(set(resolution.optional_modules), optional_keys)
        self.assertTrue(optional_keys.issubset(set(resolution.active_modules)))

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

    def test_no_runtime_install_surface(self) -> None:
        # Profiles must only reference registered optional modules — never pip specs.
        for key, profile in CAPABILITY_PROFILES.items():
            for module_key in optional_modules_for_profile(key):
                self.assertNotIn("==", module_key)
                self.assertNotIn("/", module_key)
            self.assertFalse(hasattr(profile, "pip_packages"))
