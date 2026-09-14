#!/usr/bin/env bash
# Regenerate docs/module-surface-audit.json from manifests + filesystem.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/generic-app-uv}"

uv run --project backend python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

from backend.api.router_registry import ROUTER_CONTRIBUTIONS
from backend.modules.manifests.registry import get_manifest_map

ROOT = Path(".").resolve()
MODULES_DIR = ROOT / "backend" / "modules"
FE_FEATURES = ROOT / "frontend" / "src" / "features"
FE_ROUTER = (ROOT / "frontend" / "src" / "app" / "router.tsx").read_text(encoding="utf-8")

FEATURE_HINTS = {
    "admin": (
        "admin-users",
        "admin-jobs",
        "admin-diagnostics",
        "admin-rag",
        "platform-admin",
        "settings-admin",
    ),
    "ai": ("ai",),
    "audit": (),
    "calendar": ("calendar",),
    "chat": ("chat",),
    "developer_diagnostics": ("developer-diagnostics",),
    "diagnostics": ("admin-diagnostics",),
    "identity_access": ("auth",),
    "jobs": ("admin-jobs",),
    "memory": ("profile",),
    "notifications": ("notifications",),
    "platform": ("platform", "platform-admin"),
    "policy": ("admin-users",),
    "profile": ("profile",),
    "projects": ("projects", "dashboard"),
    "rag": ("admin-rag",),
    "settings": ("settings-admin",),
    "storage": ("platform-admin",),
    "users": ("admin-users", "profile"),
}

manifest_map = get_manifest_map()
dirs = sorted(
    p.name
    for p in MODULES_DIR.iterdir()
    if p.is_dir() and p.name not in {"manifests", "__pycache__"} and not p.name.startswith(".")
)

rows: list[dict] = []
for name in dirs:
    m = manifest_map.get(name)
    tests_backend = sorted(
        str(p.relative_to(ROOT))
        for p in (MODULES_DIR / name).rglob("test_*.py")
        if "__pycache__" not in p.parts
    )
    tests_root = sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "backend" / "tests").glob(f"*{name}*")
    )
    feature_dirs = FEATURE_HINTS.get(name, (name.replace("_", "-"),))
    fe_present = [fd for fd in feature_dirs if (FE_FEATURES / fd).is_dir()]
    fe_route_hit = any(f"features/{fd}/" in FE_ROUTER for fd in feature_dirs)
    mounted_routers = []
    if m:
        for rk in m.backend_router_keys:
            mounted_routers.append(
                {
                    "router_key": rk,
                    "contribution": (
                        ROUTER_CONTRIBUTIONS[rk].import_path
                        if rk in ROUTER_CONTRIBUTIONS
                        else None
                    ),
                    "registered_in_router_registry": rk in ROUTER_CONTRIBUTIONS,
                }
            )

    if m is None:
        status = "orphan_unregistered"
    else:
        surface = getattr(m, "surface", None)
        surface_value = getattr(surface, "value", surface)
        if surface_value == "internal":
            status = "backend_internal"
        elif surface_value == "api_only":
            status = "api_only"
        elif surface_value == "embedded":
            status = "embedded"
        elif m.frontend_routes or m.nav_entries:
            status = (
                "full_stack" if (fe_route_hit or fe_present) else "manifest_ui_declared_fe_gap"
            )
        else:
            status = "registered_no_ui_surface"

    rows.append(
        {
            "module_directory": name,
            "manifest_registered": m is not None,
            "manifest_key": getattr(m, "key", None),
            "surface": getattr(getattr(m, "surface", None), "value", None),
            "embedding_host": getattr(m, "embedding_host", None),
            "always_enabled": getattr(m, "always_enabled", None),
            "optional": getattr(m, "optional", None),
            "user_visible": getattr(m, "user_visible", None),
            "backend_router_keys": list(getattr(m, "backend_router_keys", ()) or ()),
            "backend_routers_mounted": mounted_routers,
            "celery_queues": list(getattr(m, "celery_queues", ()) or ()),
            "database_requirements": list(getattr(m, "database_requirements", ()) or ()),
            "frontend_routes": [
                {"path": r.path, "page_key": r.page_key}
                for r in (getattr(m, "frontend_routes", ()) or ())
            ],
            "navigation_entries": [
                {"label": n.label, "path": n.path, "group": n.group}
                for n in (getattr(m, "nav_entries", ()) or ())
            ],
            "frontend_feature_dirs_present": fe_present,
            "frontend_router_references_feature": fe_route_hit,
            "tests": {"module_tests": tests_backend, "root_test_name_hits": tests_root},
            "status": status,
        }
    )

obs = manifest_map.get("observability")
if obs:
    rows.append(
        {
            "module_directory": "(backend/observability)",
            "manifest_registered": True,
            "manifest_key": "observability",
            "surface": obs.surface.value,
            "embedding_host": obs.embedding_host,
            "always_enabled": obs.always_enabled,
            "optional": obs.optional,
            "user_visible": obs.user_visible,
            "backend_router_keys": list(obs.backend_router_keys),
            "backend_routers_mounted": [
                {
                    "router_key": rk,
                    "contribution": (
                        ROUTER_CONTRIBUTIONS[rk].import_path
                        if rk in ROUTER_CONTRIBUTIONS
                        else None
                    ),
                    "registered_in_router_registry": rk in ROUTER_CONTRIBUTIONS,
                }
                for rk in obs.backend_router_keys
            ],
            "celery_queues": list(obs.celery_queues),
            "database_requirements": list(obs.database_requirements),
            "frontend_routes": [
                {"path": r.path, "page_key": r.page_key} for r in obs.frontend_routes
            ],
            "navigation_entries": [
                {"label": n.label, "path": n.path, "group": n.group}
                for n in obs.nav_entries
            ],
            "frontend_feature_dirs_present": (
                ["observability"] if (FE_FEATURES / "observability").is_dir() else []
            ),
            "frontend_router_references_feature": "features/observability/" in FE_ROUTER,
            "tests": {
                "module_tests": [],
                "root_test_name_hits": sorted(
                    str(p.relative_to(ROOT))
                    for p in (ROOT / "backend" / "tests").glob("*observability*")
                ),
            },
            "status": "full_stack",
        }
    )

registered_keys = set(manifest_map)
report = {
    "schema_version": 1,
    "module_directories": dirs,
    "registered_manifest_keys": sorted(registered_keys),
    "router_registry_keys": sorted(ROUTER_CONTRIBUTIONS),
    "registered_without_modules_dir": sorted(
        registered_keys - set(dirs) - {"observability"}
    ),
    "modules": sorted(rows, key=lambda r: r["module_directory"]),
    "summary": {
        "orphan_unregistered": [
            r["module_directory"] for r in rows if r["status"] == "orphan_unregistered"
        ],
        "backend_internal": [
            r["module_directory"] for r in rows if r["status"] == "backend_internal"
        ],
        "api_only": [r["module_directory"] for r in rows if r["status"] == "api_only"],
        "embedded": [r["module_directory"] for r in rows if r["status"] == "embedded"],
        "registered_no_ui_surface": [
            r["module_directory"] for r in rows if r["status"] == "registered_no_ui_surface"
        ],
        "manifest_ui_declared_fe_gap": [
            r["module_directory"]
            for r in rows
            if r["status"] == "manifest_ui_declared_fe_gap"
        ],
        "full_stack": [r["module_directory"] for r in rows if r["status"] == "full_stack"],
    },
}

out = ROOT / "docs" / "module-surface-audit.json"
out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Wrote {out}")
print(json.dumps(report["summary"], indent=2))
PY
