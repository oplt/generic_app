"""Module manifest registry and dependency validation tests."""

from __future__ import annotations

import unittest

from backend.modules.manifests import (
    REGISTERED_MANIFESTS,
    ModuleManifest,
    ModuleManifestError,
    catalog_definitions,
    effective_modules,
    validate_registry,
)
from backend.modules.manifests.validation import resolve_effective_modules, validate_manifest_graph
from backend.modules.platform.defaults import MODULE_CATALOG, MODULE_PACKS


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
        self.assertIn("rag", enabled)
        self.assertIn("ai", enabled)
        self.assertIn("storage", enabled)

    def test_missing_dependency_fails_clearly(self) -> None:
        manifests = (
            ModuleManifest(
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

    def test_enabled_optional_without_dependency_fails(self) -> None:
        manifests = (
            ModuleManifest(
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
                dependencies=("ghost",),
            ),
            ModuleManifest(
                key="ghost",
                version="1.0.0",
                label="Ghost",
                description="ghost",
                optional=True,
            ),
        )
        with self.assertRaises(ModuleManifestError) as ctx:
            resolve_effective_modules(manifests=manifests, enabled_optional=["leaf"])
        self.assertIn("missing required dependencies", str(ctx.exception).lower())

    def test_cycle_detected(self) -> None:
        manifests = (
            ModuleManifest(
                key="a",
                version="1.0.0",
                label="A",
                description="a",
                always_enabled=True,
                dependencies=("b",),
            ),
            ModuleManifest(
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
