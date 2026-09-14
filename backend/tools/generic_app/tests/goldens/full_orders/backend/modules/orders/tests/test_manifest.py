"""Smoke tests for the orders module scaffold."""

from __future__ import annotations

import unittest

from backend.modules.orders.manifest import MANIFEST


class OrdersManifestTest(unittest.TestCase):
    def test_manifest_key(self) -> None:
        self.assertEqual(MANIFEST.key, "orders")
        self.assertIn("orders", MANIFEST.backend_router_keys)
        self.assertIn("orders.read", MANIFEST.required_permissions)
