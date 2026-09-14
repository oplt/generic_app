"""Filesystem mutation journal for atomic scaffold apply/rollback."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _JournalEntry:
    path: Path
    existed: bool
    previous: str | None


@dataclass
class MutationJournal:
    """Tracks created/overwritten files so a failed run can restore state."""

    entries: list[_JournalEntry] = field(default_factory=list)
    _seen: set[Path] = field(default_factory=set)

    def record(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved in self._seen:
            return
        existed = path.exists()
        previous = path.read_text(encoding="utf-8") if existed else None
        self.entries.append(
            _JournalEntry(path=path, existed=existed, previous=previous)
        )
        self._seen.add(resolved)

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.record(path)
        path.write_text(content, encoding="utf-8")

    def rollback(self) -> None:
        for entry in reversed(self.entries):
            if entry.existed:
                entry.path.parent.mkdir(parents=True, exist_ok=True)
                entry.path.write_text(entry.previous or "", encoding="utf-8")
            elif entry.path.exists():
                entry.path.unlink()
                # Best-effort cleanup of empty parents created for the file.
                parent = entry.path.parent
                while parent.exists() and parent != parent.parent:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
        self.entries.clear()
        self._seen.clear()
