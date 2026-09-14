"""Stable marker-section helpers for deterministic source wiring."""

from __future__ import annotations

import re
from pathlib import Path

_MARKER_RE_CACHE: dict[tuple[str, str], re.Pattern[str]] = {}


class MarkerError(RuntimeError):
    """Raised when a required generated marker section is missing or malformed."""


def _pattern(open_marker: str, close_marker: str) -> re.Pattern[str]:
    key = (open_marker, close_marker)
    compiled = _MARKER_RE_CACHE.get(key)
    if compiled is None:
        # Capture optional leading indent on the open-marker line so replacements
        # preserve surrounding indentation.
        compiled = re.compile(
            r"(?P<indent>[ \t]*)"
            + re.escape(open_marker)
            + r"(.*?)"
            + re.escape(close_marker),
            re.DOTALL,
        )
        _MARKER_RE_CACHE[key] = compiled
    return compiled


def upsert_marked_block(
    text: str,
    *,
    open_marker: str,
    close_marker: str,
    lines: list[str],
    sort: bool = True,
) -> tuple[str, bool]:
    """Replace marker body with the given lines (idempotent).

    Returns ``(new_text, changed)``.
    """

    match = _pattern(open_marker, close_marker).search(text)
    if match is None:
        raise MarkerError(
            f"Missing marker block {open_marker!r} … {close_marker!r}"
        )

    indent = match.group("indent")
    body_lines = [line.rstrip("\n") for line in lines if line.strip()]
    if sort:
        body_lines = sorted(set(body_lines))
    else:
        seen: set[str] = set()
        ordered: list[str] = []
        for line in body_lines:
            if line in seen:
                continue
            seen.add(line)
            ordered.append(line)
        body_lines = ordered

    body = (
        "\n" + "\n".join(body_lines) + "\n" + indent
        if body_lines
        else "\n" + indent
    )

    replacement = f"{indent}{open_marker}{body}{close_marker}"
    start, end = match.span()
    new_text = text[:start] + replacement + text[end:]
    return new_text, new_text != text


def merge_line_into_marked_block(
    text: str,
    *,
    open_marker: str,
    close_marker: str,
    line: str,
    sort: bool = True,
) -> tuple[str, bool]:
    """Ensure ``line`` exists inside a marker block (merge with existing body)."""

    match = _pattern(open_marker, close_marker).search(text)
    if match is None:
        raise MarkerError(
            f"Missing marker block {open_marker!r} … {close_marker!r}"
        )
    existing = [raw for raw in match.group(2).splitlines() if raw.strip()]
    if line not in existing:
        existing.append(line)
    return upsert_marked_block(
        text,
        open_marker=open_marker,
        close_marker=close_marker,
        lines=existing,
        sort=sort,
    )


def merge_line_into_marked_file(
    path: Path,
    *,
    open_marker: str,
    close_marker: str,
    line: str,
    sort: bool = True,
) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, changed = merge_line_into_marked_block(
        text,
        open_marker=open_marker,
        close_marker=close_marker,
        line=line,
        sort=sort,
    )
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


def require_markers(path: Path, *markers: tuple[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for open_marker, close_marker in markers:
        if open_marker not in text or close_marker not in text:
            raise MarkerError(
                f"{path} missing required markers {open_marker!r}/{close_marker!r}"
            )
