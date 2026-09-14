"""Module manifest registry and dependency validation tests."""

from __future__ import annotations

import unittest

from backend.modules.manifests import (
    REGISTERED_MANIFESTS,
    ModuleManifest,
    ModuleManifestError,
    ModuleSurface,
    catalog_definitions,
    effective_modules,
    validate_registry,
)
from backend.modules.manifests.types import FrontendRoute, NavEntry
from backend.modules.manifests.validation import resolve_effective_modules, validate_manifest_graph
from backend.modules.platform.defaults import MODULE_CATALOG, MODULE_PACKS


def _internal(**kwargs) -> ModuleManifest:
    return ModuleManifest(
        surface=ModuleSurface.INTERNAL,
        user_visible=False,
        **kwargs,
    )


class ModuleManifestRegistryTest(unittest.TestCase):
    def test_registry_validates_cleanly(self) -> None:
        validate_registry()

    def test_optional_catalog_matches_defaults(self) -> None:
        catalog_keys = {item["key"] for item in catalog_definitions()}
        default_keys = {item["key"] for item in MODULE_CATALOG}
        self.assertEqual(catalog_keys, default_keys)
        self.assertIn("billing", catalog_keys)
        self.assertNotIn("projects", catalog_keys)  # always-on core

    def test_packs_only_reference_known_modules(self) -> None:
        known = {manifest.key for manifest in REGISTERED_MANIFESTS}
        for pack_key, pack in MODULE_PACKS.items():
            unknown = set(pack["modules"]) - known
            self.assertFalse(unknown, f"pack {pack_key} has unknown modules: {unknown}")

    def test_effective_modules_includes_always_on_and_optional(self) -> None:
        enabled = effective_modules(["billing", "webhooks"])
        self.assertIn("billing", enabled)
        self.assertIn("webhooks", enabled)
        self.assertIn("projects", enabled)
        self.assertIn("storage", enabled)
        self.assertIn("audit", enabled)
        # Specialists are profile-selected, not always-on.
        self.assertNotIn("rag", enabled)
        self.assertNotIn("ai", enabled)

    def test_audit_is_registered_backend_internal(self) -> None:
        manifests = {m.key: m for m in REGISTERED_MANIFESTS}
        self.assertIn("audit", manifests)
        audit = manifests["audit"]
        self.assertTrue(audit.always_enabled)
        self.assertFalse(audit.user_visible)
        self.assertEqual(audit.surface, ModuleSurface.INTERNAL)
        self.assertEqual(audit.frontend_routes, ())
        self.assertEqual(audit.nav_entries, ())
        self.assertIn("audit_logs", audit.database_requirements)
        self.assertIn("audit", manifests["admin"].dependencies)

    def test_api_only_and_embedded_surfaces_are_explicit(self) -> None:
        by_key = {m.key: m for m in REGISTERED_MANIFESTS}
        self.assertEqual(by_key["policy"].surface, ModuleSurface.EMBEDDED)
        self.assertEqual(by_key["policy"].embedding_host, "admin.users")
        self.assertEqual(by_key["memory"].surface, ModuleSurface.EMBEDDED)
        self.assertEqual(by_key["memory"].embedding_host, "profile.settings")
        self.assertEqual(by_key["developer_diagnostics"].surface, ModuleSurface.EMBEDDED)
        self.assertEqual(by_key["developer_diagnostics"].embedding_host, "app.shell")
        self.assertEqual(by_key["users"].surface, ModuleSurface.EMBEDDED)

    def test_user_facing_without_routes_fails(self) -> None:
        manifests = (
            ModuleManifest(
                key="lonely",
                version="1.0.0",
                label="Lonely",
                description="lonely",
                always_enabled=True,
                surface=ModuleSurface.USER_FACING,
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests)
        self.assertIn("frontend_routes", str(ctx.exception))

    def test_nav_must_resolve_to_frontend_route(self) -> None:
        manifests = (
            ModuleManifest(
                key="broken",
                version="1.0.0",
                label="Broken",
                description="broken",
                always_enabled=True,
                surface=ModuleSurface.USER_FACING,
                frontend_routes=(FrontendRoute(path="/ok", page_key="dashboard.main"),),
                nav_entries=(NavEntry(label="Nope", path="/missing"),),
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests, known_page_keys={"dashboard.main"})
        self.assertIn("nav path", str(ctx.exception).lower())

    def test_unknown_backend_router_key_fails(self) -> None:
        manifests = (
            ModuleManifest(
                key="ghost_api",
                version="1.0.0",
                label="Ghost",
                description="ghost",
                always_enabled=True,
                surface=ModuleSurface.API_ONLY,
                user_visible=False,
                backend_router_keys=("not_a_real_router",),
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests, router_keys={"auth"})
        self.assertIn("unknown backend_router_keys", str(ctx.exception))

    def test_unknown_page_key_fails(self) -> None:
        manifests = (
            ModuleManifest(
                key="pages",
                version="1.0.0",
                label="Pages",
                description="pages",
                always_enabled=True,
                surface=ModuleSurface.USER_FACING,
                frontend_routes=(FrontendRoute(path="/x", page_key="does.not.exist"),),
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests, known_page_keys={"dashboard.main"})
        self.assertIn("unknown page_key", str(ctx.exception))

    def test_effective_modules_can_select_specialists(self) -> None:
        enabled = effective_modules([], enabled_selected=["rag"])
        self.assertIn("rag", enabled)
        self.assertIn("ai", enabled)  # dependency closure
        self.assertIn("storage", enabled)
        self.assertNotIn("chat", enabled)

    def test_missing_dependency_fails_clearly(self) -> None:
        manifests = (
            _internal(
                key="alpha",
                version="1.0.0",
                label="Alpha",
                description="alpha",
                always_enabled=True,
                dependencies=("missing_dep",),
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests)
        self.assertIn("unknown module", str(ctx.exception).lower())

    def test_enabled_optional_closes_dependencies_by_default(self) -> None:
        manifests = (
            _internal(
                key="core",
                version="1.0.0",
                label="Core",
                description="core",
                always_enabled=True,
            ),
            ModuleManifest(
                key="leaf",
                version="1.0.0",
                label="Leaf",
                description="leaf",
                optional=True,
                surface=ModuleSurface.EMBEDDED,
                embedding_host="core.host",
                dependencies=("ghost",),
            ),
            ModuleManifest(
                key="ghost",
                version="1.0.0",
                label="Ghost",
                description="ghost",
                optional=True,
                surface=ModuleSurface.EMBEDDED,
                embedding_host="core.host",
            ),
        )
        enabled = resolve_effective_modules(manifests=manifests, enabled_optional=["leaf"])
        self.assertIn("leaf", enabled)
        self.assertIn("ghost", enabled)

    def test_enabled_optional_without_dependency_fails_when_not_closing(self) -> None:
        manifests = (
            _internal(
                key="core",
                version="1.0.0",
                label="Core",
                description="core",
                always_enabled=True,
            ),
            ModuleManifest(
                key="leaf",
                version="1.0.0",
                label="Leaf",
                description="leaf",
                optional=True,
                surface=ModuleSurface.EMBEDDED,
                embedding_host="core.host",
                dependencies=("ghost",),
            ),
            ModuleManifest(
                key="ghost",
                version="1.0.0",
                label="Ghost",
                description="ghost",
                optional=True,
                surface=ModuleSurface.EMBEDDED,
                embedding_host="core.host",
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            resolve_effective_modules(
                manifests=manifests,
                enabled_optional=["leaf"],
                close_dependencies=False,
            )
        self.assertIn("missing required dependencies", str(ctx.exception).lower())

    def test_cycle_detected(self) -> None:
        manifests = (
            _internal(
                key="a",
                version="1.0.0",
                label="A",
                description="a",
                always_enabled=True,
                dependencies=("b",),
            ),
            _internal(
                key="b",
                version="1.0.0",
                label="B",
                description="b",
                always_enabled=True,
                dependencies=("a",),
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            validate_manifest_graph(manifests)
        self.assertIn("cycle", str(ctx.exception).lower())

    def test_rag_declares_ai_and_storage_dependencies(self) -> None:
        rag = next(m for m in REGISTERED_MANIFESTS if m.key == "rag")
        self.assertIn("ai", rag.dependencies)
        self.assertIn("storage", rag.dependencies)
