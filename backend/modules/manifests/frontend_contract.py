"""Frontend page_key allow-list contract shared with the React page registry.

``frontend/src/app/pageKeys.json`` is the single source of registered page keys.
Manifests may only declare ``FrontendRoute.page_key`` values present here.
The frontend ``pageRegistry`` must implement every key.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PAGE_KEYS_PATH = _REPO_ROOT / "frontend" / "src" / "app" / "pageKeys.json"


@lru_cache(maxsize=1)
def load_registered_page_keys() -> frozenset[str]:
    payload = json.loads(_PAGE_KEYS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError(f"{_PAGE_KEYS_PATH} must be a JSON array of strings")
    return frozenset(payload)


def registered_page_keys_path() -> Path:
    return _PAGE_KEYS_PATH
