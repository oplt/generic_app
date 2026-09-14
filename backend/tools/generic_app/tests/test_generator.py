"""Tests for generic-app module scaffold generator."""

from __future__ import annotations

import ast
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from backend.tools.generic_app.alembic_resolve import (
    AlembicResolveError,
    resolve_alembic_down_revision,
)
from backend.tools.generic_app.cli import main
from backend.tools.generic_app.create_module import (
    GeneratorOptions,
    create_module,
    render_module,
)
from backend.tools.generic_app.naming import ModuleNames
from backend.tools.generic_app.wiring import (
    WiringError,
    apply_all_wiring,
)

GOLDENS = Path(__file__).resolve().parent / "goldens"
REPO_ROOT = Path(__file__).resolve().parents[4]


def _ignore_noise(path: Path) -> bool:
    return (
        path.name == "__pycache__"
        or path.suffix in {".pyc", ".pyo"}
        or ".pytest_cache" in path.parts
    )


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
            enablement="optional",
        )
        files = {
            item.relative_path: item.content
            for item in render_module(
                names, options, down_revision="l2b9d4e5f150"
            )
        }
        self._assert_golden("full_orders", files)

    def test_generated_python_parses(self) -> None:
        names = ModuleNames.from_key("orders")
        options = GeneratorOptions(
            crud=True,
            celery=True,
            permissions=True,
            events=True,
            wire=False,
            enablement="optional",
        )
        for item in render_module(names, options, down_revision="l2b9d4e5f150"):
            if item.relative_path.endswith(".py"):
                try:
                    ast.parse(item.content)
                except SyntaxError as exc:
                    self.fail(f"Syntax error in {item.relative_path}: {exc}")

    def test_enablement_variants(self) -> None:
        names = ModuleNames.from_key("widgets")
        optional = render_module(
            names, GeneratorOptions(enablement="optional")
        )
        core = render_module(names, GeneratorOptions(enablement="core"))
        profile = render_module(
            names, GeneratorOptions(enablement="profile", profile="rag")
        )
        optional_manifest = next(
            item.content for item in optional if item.relative_path.endswith("manifest.py")
        )
        core_manifest = next(
            item.content for item in core if item.relative_path.endswith("manifest.py")
        )
        profile_manifest = next(
            item.content for item in profile if item.relative_path.endswith("manifest.py")
        )
        self.assertIn("always_enabled=False", optional_manifest)
        self.assertIn("optional=True", optional_manifest)
        self.assertIn("always_enabled=True", core_manifest)
        self.assertIn("optional=False", core_manifest)
        self.assertIn("always_enabled=False", profile_manifest)
        self.assertIn("optional=False", profile_manifest)

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
            if path.is_file() and not _ignore_noise(path)
        }
        self.assertEqual(expected_paths, set(files))
        for relative, content in files.items():
            expected = (golden_root / relative).read_text(encoding="utf-8")
            self.assertEqual(
                content,
                expected,
                msg=f"Golden drift for {suite}/{relative}",
            )


class AlembicResolveTest(unittest.TestCase):
    def test_repo_has_single_head(self) -> None:
        head = resolve_alembic_down_revision(REPO_ROOT)
        self.assertEqual(head, "n4d1f6a7b372")

    def test_multi_head_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alembic = root / "backend" / "alembic"
            versions = alembic / "versions"
            versions.mkdir(parents=True)
            (root / "backend" / "alembic.ini").write_text(
                "[alembic]\nscript_location = backend/alembic\n",
                encoding="utf-8",
            )
            (alembic / "env.py").write_text("# stub\n", encoding="utf-8")
            (alembic / "script.py.mako").write_text("", encoding="utf-8")
            for rev, parent in (("aaaa", None), ("bbbb", None)):
                (versions / f"{rev}_x.py").write_text(
                    f'revision = "{rev}"\ndown_revision = {parent!r}\n'
                    "branch_labels = None\ndepends_on = None\n"
                    "def upgrade():\n    pass\n"
                    "def downgrade():\n    pass\n",
                    encoding="utf-8",
                )
            with self.assertRaises(AlembicResolveError):
                resolve_alembic_down_revision(root)


class MarkerWiringTest(unittest.TestCase):
    def _stub_repo(self, root: Path) -> None:
        registry = root / "backend/modules/manifests/registry.py"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            (
                "# <generic-app:manifest-imports>\n"
                "# </generic-app:manifest-imports>\n"
                "REGISTERED_MANIFESTS = (\n"
                "    # <generic-app:manifest-entries>\n"
                "    # </generic-app:manifest-entries>\n"
                ")\n"
            ),
            encoding="utf-8",
        )
        router = root / "backend/api/router_registry.py"
        router.parent.mkdir(parents=True)
        router.write_text(
            (
                "ROUTER_CONTRIBUTIONS = {\n"
                "    # <generic-app:router-contributions>\n"
                "    # </generic-app:router-contributions>\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        env = root / "backend/alembic/env.py"
        env.parent.mkdir(parents=True)
        env.write_text(
            "# <generic-app:model-imports>\n# </generic-app:model-imports>\n",
            encoding="utf-8",
        )
        catalog = root / "backend/modules/policy/catalog.py"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(
            (
                "# <generic-app:permission-constants>\n"
                "# </generic-app:permission-constants>\n"
                "ALL_PERMISSIONS = (\n"
                "    # <generic-app:permission-entries>\n"
                "    # </generic-app:permission-entries>\n"
                ")\n"
            ),
            encoding="utf-8",
        )
        celery = root / "backend/modules/manifests/celery_contrib.py"
        celery.write_text(
            (
                "MODULE_TASK_ROUTES = {\n"
                "    # <generic-app:task-routes>\n"
                "    # </generic-app:task-routes>\n"
                "}\n"
                "GENERATED_TASK_MODULES = (\n"
                "    # <generic-app:task-modules>\n"
                "    # </generic-app:task-modules>\n"
                ")\n"
            ),
            encoding="utf-8",
        )
        profiles = root / "backend/modules/platform/profiles.py"
        profiles.parent.mkdir(parents=True)
        profiles.write_text(
            (
                "PROFILE_EXTRA_MODULES = {\n"
                "    # <generic-app:profile-extra-modules>\n"
                "    # </generic-app:profile-extra-modules>\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        fe = root / "frontend/src/app/router.tsx"
        fe.parent.mkdir(parents=True)
        fe.write_text(
            (
                "// <generic-app:lazy-imports>\n"
                "// </generic-app:lazy-imports>\n"
                "export function AppRouter() {\n"
                "  return (\n"
                "    <>\n"
                "      {/* <generic-app:routes> */}\n"
                "      {/* </generic-app:routes> */}\n"
                "    </>\n"
                "  );\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        (root / "frontend/src").mkdir(parents=True, exist_ok=True)
        (root / "backend/modules").mkdir(parents=True, exist_ok=True)
        (root / "backend/alembic/versions").mkdir(parents=True, exist_ok=True)
        (root / "backend/alembic.ini").write_text(
            "[alembic]\nscript_location = backend/alembic\n",
            encoding="utf-8",
        )
        (root / "backend/alembic/script.py.mako").write_text("", encoding="utf-8")
        (root / "backend/alembic/versions/aaaa_head.py").write_text(
            'revision = "aaaa"\ndown_revision = None\n'
            "branch_labels = None\ndepends_on = None\n"
            "def upgrade():\n    pass\n"
            "def downgrade():\n    pass\n",
            encoding="utf-8",
        )

    def test_wires_markers_idempotently(self) -> None:
        names = ModuleNames.from_key("orders")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._stub_repo(root)
            first = apply_all_wiring(
                root,
                names,
                crud=True,
                permissions=True,
                celery=True,
                frontend=True,
                profile="rag",
            )
            second = apply_all_wiring(
                root,
                names,
                crud=True,
                permissions=True,
                celery=True,
                frontend=True,
                profile="rag",
            )
            self.assertTrue(first)
            self.assertEqual(second, [])
            registry = (root / "backend/modules/manifests/registry.py").read_text()
            self.assertIn("MANIFEST as ORDERS", registry)
            self.assertEqual(registry.count("MANIFEST as ORDERS"), 1)
            router = (root / "backend/api/router_registry.py").read_text()
            self.assertIn('"orders": RouterContribution', router)
            celery = (root / "backend/modules/manifests/celery_contrib.py").read_text()
            self.assertIn("orders.example_task", celery)
            self.assertIn("backend.modules.orders.workers", celery)
            fe = (root / "frontend/src/app/router.tsx").read_text()
            self.assertIn("OrdersListPage", fe)
            self.assertIn('pageKey="orders.list"', fe)
            profiles = (root / "backend/modules/platform/profiles.py").read_text()
            self.assertIn('"rag": ("orders",)', profiles)

    def test_missing_marker_fails(self) -> None:
        names = ModuleNames.from_key("orders")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._stub_repo(root)
            (root / "backend/api/router_registry.py").write_text(
                "ROUTER_CONTRIBUTIONS = {}\n", encoding="utf-8"
            )
            with self.assertRaises(WiringError):
                apply_all_wiring(
                    root,
                    names,
                    crud=False,
                    permissions=False,
                    celery=False,
                    frontend=False,
                    profile=None,
                )


class AtomicGenerationTest(unittest.TestCase):
    def test_rollback_on_wiring_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend/modules").mkdir(parents=True)
            (root / "frontend/src").mkdir(parents=True)
            # Intentionally missing marker targets so wiring fails after writes.
            with self.assertRaises(RuntimeError) as ctx:
                create_module(
                    "broken_mod",
                    options=GeneratorOptions(crud=False, wire=True, force=True),
                    repo_root=root,
                )
            self.assertIn("rolled back", str(ctx.exception).lower())
            self.assertFalse((root / "backend/modules/broken_mod").exists())

    def test_dry_run_writes_nothing(self) -> None:
        result = create_module(
            "widgets",
            options=GeneratorOptions(crud=True, wire=False),
            repo_root=REPO_ROOT,
            dry_run=True,
        )
        self.assertTrue(any("Dry run" in note for note in result.notes))
        self.assertFalse((REPO_ROOT / "backend/modules/widgets").exists())


class LiveImportSmokeTest(unittest.TestCase):
    def test_generated_module_imports_cleanly(self) -> None:
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
                    crud=True,
                    permissions=True,
                    wire=False,
                    force=True,
                    enablement="optional",
                ),
                repo_root=REPO_ROOT,
            )
            from backend.modules.zz_scaffold_smoke.api.router import (  # noqa: WPS433
                router as smoke_router,
            )

            self.assertTrue(smoke_router.routes)
            manifest = (
                REPO_ROOT / "backend/modules/zz_scaffold_smoke/manifest.py"
            ).read_text(encoding="utf-8")
            self.assertIn("always_enabled=False", manifest)
            self.assertIn("optional=True", manifest)
        finally:
            if module_dir.exists():
                shutil.rmtree(module_dir)
            for path in (REPO_ROOT / "backend" / "alembic" / "versions").glob(
                f"*add_{module_key}_table.py"
            ):
                path.unlink(missing_ok=True)
            sys.modules.pop("backend.modules.zz_scaffold_smoke", None)
            sys.modules.pop("backend.modules.zz_scaffold_smoke.api", None)
            sys.modules.pop("backend.modules.zz_scaffold_smoke.api.router", None)


# Prevent pytest from collecting golden fixture trees as tests.
collect_ignore_glob = ["goldens/*"]
