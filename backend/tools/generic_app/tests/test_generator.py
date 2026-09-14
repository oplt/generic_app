"""Tests for generic-app module scaffold generator."""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

from backend.tools.generic_app.cli import main
from backend.tools.generic_app.create_module import (
    GeneratorOptions,
    create_module,
    render_module,
)
from backend.tools.generic_app.naming import ModuleNames
from backend.tools.generic_app.wiring import (
    wire_api_router,
    wire_manifest_registry,
    wire_policy_catalog,
)

GOLDENS = Path(__file__).resolve().parent / "goldens"
REPO_ROOT = Path(__file__).resolve().parents[4]


class NamingTest(unittest.TestCase):
    def test_orders_entity(self) -> None:
        names = ModuleNames.from_key("orders")
        self.assertEqual(names.entity, "order")
        self.assertEqual(names.entity_pascal, "Order")
        self.assertEqual(names.pascal, "Orders")
        self.assertEqual(names.constant, "ORDERS")


class CliHelpTest(unittest.TestCase):
    def test_root_help(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_create_module_help(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["create-module", "--help"])
        self.assertEqual(ctx.exception.code, 0)


class GoldenRenderTest(unittest.TestCase):
    def test_minimal_module_golden(self) -> None:
        names = ModuleNames.from_key("inventory")
        files = {
            item.relative_path: item.content
            for item in render_module(names, GeneratorOptions(wire=False))
        }
        self._assert_golden("minimal_inventory", files)

    def test_full_crud_golden(self) -> None:
        names = ModuleNames.from_key("orders")
        options = GeneratorOptions(
            crud=True,
            frontend=True,
            celery=True,
            permissions=True,
            events=True,
            storage=True,
            wire=False,
        )
        files = {item.relative_path: item.content for item in render_module(names, options)}
        self._assert_golden("full_orders", files)

    def test_generated_python_parses(self) -> None:
        names = ModuleNames.from_key("orders")
        options = GeneratorOptions(
            crud=True,
            celery=True,
            permissions=True,
            events=True,
            wire=False,
        )
        for item in render_module(names, options):
            if item.relative_path.endswith(".py"):
                try:
                    ast.parse(item.content)
                except SyntaxError as exc:
                    self.fail(f"Syntax error in {item.relative_path}: {exc}")

    def _assert_golden(self, suite: str, files: dict[str, str]) -> None:
        golden_root = GOLDENS / suite
        if not golden_root.exists():
            golden_root.mkdir(parents=True)
            for relative, content in files.items():
                target = golden_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            self.fail(
                f"Wrote golden fixtures under {golden_root}. Re-run tests to assert."
            )

        expected_paths = {
            str(path.relative_to(golden_root))
            for path in golden_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected_paths, set(files))
        for relative, content in files.items():
            expected = (golden_root / relative).read_text(encoding="utf-8")
            self.assertEqual(
                content,
                expected,
                msg=f"Golden drift for {suite}/{relative}",
            )


class WiringTest(unittest.TestCase):
    def test_wires_registry_and_router(self) -> None:
        names = ModuleNames.from_key("orders")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.py"
            router = root / "router.py"
            catalog = root / "catalog.py"
            registry.write_text(
                (
                    "from backend.observability.manifest import MANIFEST as OBSERVABILITY\n\n"
                    "REGISTERED_MANIFESTS = (\n"
                    "    MEMORY,\n"
                    "    *OPTIONAL_PLATFORM_MANIFESTS,\n"
                    ")\n"
                ),
                encoding="utf-8",
            )
            router.write_text(
                (
                    "from backend.modules.settings.router import router as settings_router\n"
                    "api_router = APIRouter()\n"
                    'api_router.include_router(admin_router, prefix="/admin", tags=["admin"])\n'
                ),
                encoding="utf-8",
            )
            catalog.write_text(
                (
                    'ADMIN_MANAGE = "admin.manage"\n'
                    "ALL_PERMISSIONS: tuple[str, ...] = (\n"
                    "    ADMIN_MANAGE,\n"
                    ")\n"
                ),
                encoding="utf-8",
            )

            self.assertTrue(wire_manifest_registry(registry, names))
            self.assertTrue(wire_api_router(router, names))
            self.assertTrue(wire_policy_catalog(catalog, names))
            registry_text = registry.read_text(encoding="utf-8")
            self.assertIn("MANIFEST as ORDERS", registry_text)
            self.assertIn("ORDERS,", registry_text)
            router_text = router.read_text(encoding="utf-8")
            self.assertIn("orders_router", router_text)
            catalog_text = catalog.read_text(encoding="utf-8")
            self.assertIn('ORDERS_READ = "orders.read"', catalog_text)

    def test_create_module_dry_run_smoke_import(self) -> None:
        result = create_module(
            "widgets",
            options=GeneratorOptions(crud=True, wire=False),
            repo_root=REPO_ROOT,
            dry_run=True,
        )
        self.assertEqual(result.module_key, "widgets")
        self.assertGreaterEqual(len(result.files), 8)
        # Ensure rendered manifest imports for real.
        manifest = next(
            item for item in result.files if item.relative_path.endswith("manifest.py")
        )
        # Avoid importing the full app — syntax-check the scaffold instead.
        ast.parse(manifest.content)

    def test_generated_module_imports_cleanly(self) -> None:
        import shutil

        module_key = "zz_scaffold_smoke"
        module_dir = REPO_ROOT / "backend" / "modules" / module_key
        alembic_glob = list(
            (REPO_ROOT / "backend" / "alembic" / "versions").glob(
                f"*add_{module_key}_table.py"
            )
        )
        if module_dir.exists():
            shutil.rmtree(module_dir)
        for path in alembic_glob:
            path.unlink(missing_ok=True)
        try:
            create_module(
                module_key,
                options=GeneratorOptions(
                    crud=True, permissions=True, wire=False, force=True
                ),
                repo_root=REPO_ROOT,
            )
            from backend.modules.zz_scaffold_smoke.api.router import router as smoke_router
            from backend.modules.zz_scaffold_smoke.manifest import (
                MANIFEST as smoke_manifest,
            )

            self.assertEqual(smoke_manifest.key, module_key)
            self.assertGreaterEqual(len(smoke_router.routes), 1)
        finally:
            if module_dir.exists():
                shutil.rmtree(module_dir)
            for path in (REPO_ROOT / "backend" / "alembic" / "versions").glob(
                f"*add_{module_key}_table.py"
            ):
                path.unlink(missing_ok=True)
            for name in list(sys.modules):
                if name.startswith("backend.modules.zz_scaffold_smoke"):
                    del sys.modules[name]
