"""Smoke tests for the orders module scaffold."""

from __future__ import annotations

import unittest

from backend.modules.manifests.types import ModuleSurface
from backend.modules.orders.manifest import MANIFEST


class OrdersManifestTest(unittest.TestCase):
    def test_manifest_key(self) -> None:
        self.assertEqual(MANIFEST.key, "orders")
        self.assertIn("orders", MANIFEST.backend_router_keys)
        self.assertEqual(MANIFEST.surface, ModuleSurface.USER_FACING)
        self.assertTrue(MANIFEST.frontend_routes)
        self.assertEqual(MANIFEST.frontend_routes[0].page_key, "orders.list")
        self.assertIn("orders.read", MANIFEST.required_permissions)
