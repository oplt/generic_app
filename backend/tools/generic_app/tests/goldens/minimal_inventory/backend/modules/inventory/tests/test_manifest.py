"""Smoke tests for the inventory module scaffold."""

from __future__ import annotations

import unittest

from backend.modules.manifests.types import ModuleSurface
from backend.modules.inventory.manifest import MANIFEST


class InventoryManifestTest(unittest.TestCase):
    def test_manifest_key(self) -> None:
        self.assertEqual(MANIFEST.key, "inventory")
        self.assertIn("inventory", MANIFEST.backend_router_keys)
        self.assertEqual(MANIFEST.surface, ModuleSurface.API_ONLY)
        self.assertFalse(MANIFEST.frontend_routes)
