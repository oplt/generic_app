"""Architecture guards for hotspot decompositions and module boundaries."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _imports_from(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


class HotspotDecompositionTest(unittest.TestCase):
    def test_settings_service_is_database_focused(self):
        path = BACKEND / "modules/settings/service.py"
        text = path.read_text()
        self.assertNotIn("CONFIG_FIELD_METADATA =", text)
        self.assertIn("ConfigSettingsService", text)
        self.assertLess(len(text.splitlines()), 200)

    def test_config_catalog_has_no_database_dependency(self):
        imports = _imports_from(BACKEND / "modules/settings/config_catalog.py")
        self.assertTrue(
            all(
                "sqlalchemy" not in name and ".repository" not in name
                for name in imports
            )
        )

    def test_rag_routes_compose_resource_routers(self):
        text = (BACKEND / "modules/rag/api/routes.py").read_text()
        self.assertIn("document_router", text)
        self.assertIn("query_router", text)
        self.assertIn("job_router", text)
        self.assertLess(len(text.splitlines()), 40)

    def test_chat_context_helpers_are_pure(self):
        imports = _imports_from(BACKEND / "modules/chat/application/chat_context.py")
        self.assertNotIn("sqlalchemy.ext.asyncio", imports)
        self.assertTrue(all("repository" not in name for name in imports))

    def test_no_cross_module_router_imports_in_hotspots(self):
        forbidden_prefixes = (
            "backend.modules.projects.router",
            "backend.modules.settings.router",
            "backend.modules.rag.api.routes",
            "backend.modules.chat.api",
        )
        hotspot_files = [
            BACKEND / "modules/chat/service.py",
            BACKEND / "modules/memory/application/memory_service.py",
            BACKEND / "modules/settings/service.py",
            BACKEND / "modules/settings/config_settings_service.py",
        ]
        for path in hotspot_files:
            imports = _imports_from(path)
            for name in imports:
                for prefix in forbidden_prefixes:
                    self.assertFalse(
                        name == prefix or name.startswith(prefix + "."),
                        f"{path.name} imports {name}",
                    )


class ImportCycleSmokeTest(unittest.TestCase):
    def test_hotspot_modules_import(self):
        from backend.modules.chat.application.chat_context import bounded_token_batches
        from backend.modules.chat.service import DocumentChatService
        from backend.modules.memory.application.memory_service import MemoryService
        from backend.modules.memory.application.memory_turn_processor import (
            process_turn_memories,
        )
        from backend.modules.rag.api.routes import list_document_chunks, router
        from backend.modules.settings.config_settings_service import ConfigSettingsService
        from backend.modules.settings.service import SettingsService

        self.assertTrue(callable(bounded_token_batches))
        self.assertTrue(callable(DocumentChatService))
        self.assertTrue(callable(MemoryService))
        self.assertTrue(callable(process_turn_memories))
        self.assertTrue(callable(list_document_chunks))
        self.assertIsNotNone(router)
        self.assertTrue(callable(ConfigSettingsService.list_config_entries))
        self.assertTrue(callable(SettingsService.list_config_entries))


if __name__ == "__main__":
    unittest.main()
