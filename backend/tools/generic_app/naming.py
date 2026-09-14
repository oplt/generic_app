"""Naming helpers for module scaffolding."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MODULE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_module_key(key: str) -> str:
    if not _MODULE_KEY_RE.match(key):
        raise ValueError(
            f"Invalid module name {key!r}. Use lowercase snake_case "
            "(letters, digits, underscore; must start with a letter)."
        )
    return key


def singularize(name: str) -> str:
    if name.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if name.endswith(("sses", "ches", "shes", "xes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss") and len(name) > 1:
        return name[:-1]
    return name


def to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def to_title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("_") if part)


@dataclass(frozen=True, slots=True)
class ModuleNames:
    key: str
    label: str
    pascal: str
    entity: str
    entity_pascal: str
    table: str
    constant: str
    permission_prefix: str

    @classmethod
    def from_key(cls, key: str, *, entity: str | None = None) -> ModuleNames:
        key = validate_module_key(key)
        entity_key = validate_module_key(entity) if entity else singularize(key)
        return cls(
            key=key,
            label=to_title(key),
            pascal=to_pascal(key),
            entity=entity_key,
            entity_pascal=to_pascal(entity_key),
            table=key,
            constant=key.upper(),
            permission_prefix=key,
        )
