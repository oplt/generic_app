"""Architectural rules for module manifests, profiles, and config construction."""

from __future__ import annotations

import unittest

from backend.api.router_registry import ROUTER_CONTRIBUTIONS
from backend.core.config import Settings
from backend.core.openapi_export import OPENAPI_EXPORT_ENV
from backend.modules.manifests import REGISTERED_MANIFESTS, validate_registry
from backend.modules.manifests.frontend_contract import load_registered_page_keys
from backend.modules.platform.profiles import (
    CAPABILITY_PROFILES,
    resolve_active_modules,
    validate_capability_profiles,
)
from backend.modules.policy import catalog


class ArchitectureRulesTest(unittest.TestCase):
    def test_manifest_keys_are_unique(self) -> None:
        keys = [manifest.key for manifest in REGISTERED_MANIFESTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_registry_and_capability_profiles_validate(self) -> None:
        validate_registry()
        validate_capability_profiles()

    def test_backend_router_keys_exist_in_router_registry(self) -> None:
        known = set(ROUTER_CONTRIBUTIONS)
        for manifest in REGISTERED_MANIFESTS:
            unknown = set(manifest.backend_router_keys) - known
            self.assertFalse(
                unknown,
                f"{manifest.key} declares unknown router keys: {sorted(unknown)}",
            )

    def test_frontend_page_keys_are_in_allow_list(self) -> None:
        allowed = load_registered_page_keys()
        for manifest in REGISTERED_MANIFESTS:
            for route in manifest.frontend_routes:
                self.assertIn(
                    route.page_key,
                    allowed,
                    f"{manifest.key} route {route.path} uses unknown page_key {route.page_key}",
                )

    def test_required_permissions_exist_in_catalog(self) -> None:
        known = set(catalog.ALL_PERMISSIONS)
        for manifest in REGISTERED_MANIFESTS:
            unknown = set(manifest.required_permissions) - known
            self.assertFalse(
                unknown,
                f"{manifest.key} declares unknown permissions: {sorted(unknown)}",
            )

    def test_named_profiles_resolve_distinct_capability_slices(self) -> None:
        core = resolve_active_modules("core")
        rag = resolve_active_modules("rag")
        self.assertNotIn("rag", core.active_modules)
        self.assertNotIn("ai", core.active_modules)
        self.assertIn("rag", rag.active_modules)
        self.assertIn("ai", rag.active_modules)
        self.assertIn("storage", rag.health_checks)
        self.assertNotIn("storage", core.health_checks)

    def test_every_capability_profile_is_registered(self) -> None:
        self.assertGreaterEqual(len(CAPABILITY_PROFILES), 5)
        for key in CAPABILITY_PROFILES:
            resolution = resolve_active_modules(key)
            self.assertEqual(resolution.profile_key, key)
            self.assertTrue(resolution.active_modules)

    def test_settings_constructs_for_openapi_export_and_defaults(self) -> None:
        export = Settings.for_openapi_export()
        self.assertEqual(export.APP_ENV, "dev")
        self.assertFalse(export.STORAGE_AUTO_CREATE_BUCKET)
        for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET"):
            self.assertIn(key, OPENAPI_EXPORT_ENV)


if __name__ == "__main__":
    unittest.main()
