"""Regression: admin metrics collapses user COUNTs into one query."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


class AdminMetricsQueryShapeTest(unittest.TestCase):
    def test_user_counts_use_single_select(self) -> None:
        source = Path("backend/modules/admin/router.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        metrics_fn = None
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_metrics":
                metrics_fn = node
                break
        self.assertIsNotNone(metrics_fn)
        text = ast.get_source_segment(source, metrics_fn) or ""
        # Three filtered user counts must not each open their own scalar() call.
        self.assertLessEqual(text.count("db.scalar("), 1)
        self.assertIn("func.count().filter(User.is_verified", text)
        self.assertIn("func.count().filter(User.is_active", text)
