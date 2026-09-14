from __future__ import annotations

import re
from datetime import UTC, datetime

from backend.modules.memory.domain.models import MemoryItem


class MemoryConsolidator:
    """Merge duplicates and prefer newer confirmed facts."""

    def consolidate(self, items: list[MemoryItem]) -> list[MemoryItem]:
        if not items:
            return []

        grouped: dict[str, MemoryItem] = {}
        for item in items:
            key = self._similarity_key(item.content)
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = item
                continue
            grouped[key] = self._pick_preferred(existing, item)
        return self.mark_contradictions(self.calibrate_confidence(list(grouped.values())))

    def calibrate_confidence(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Apply retrieval evidence and bounded recency decay to stored confidence."""
        now = datetime.now(UTC)
        for item in items:
            confidence = max(0.0, min(1.0, item.metadata.confidence))
            if item.score is not None:
                confidence = (confidence * 0.7) + (max(0.0, min(1.0, item.score)) * 0.3)
            reference = item.metadata.last_confirmed_at or item.metadata.created_at
            if reference:
                age_days = max(0.0, (now - reference).total_seconds() / 86400)
                confidence *= max(0.75, 1.0 - (age_days / 3650))
            item.metadata.confidence = round(confidence, 4)
        return items

    def mark_contradictions(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Drop older contradicted items when a newer confirmed fact exists."""
        by_type: dict[str, list[MemoryItem]] = {}
        for item in items:
            key = f"{item.metadata.memory_type.value}:{item.metadata.memory_level.value}"
            by_type.setdefault(key, []).append(item)

        result: list[MemoryItem] = []
        for group in by_type.values():
            if len(group) == 1:
                result.append(group[0])
                continue
            group.sort(key=self._recency_score, reverse=True)
            winner = group[0]
            for challenger in group[1:]:
                if self._contradicts(winner.content, challenger.content):
                    continue
                result.append(challenger)
            result.append(winner)
        return result

    def _similarity_key(self, content: str) -> str:
        normalized = " ".join(content.lower().split())
        return normalized[:160]

    def _recency_score(self, item: MemoryItem) -> float:
        confirmed = item.metadata.last_confirmed_at or item.metadata.created_at
        seen = item.metadata.last_seen_at or confirmed
        base = 0.0
        if confirmed:
            base += confirmed.timestamp()
        if seen:
            base += seen.timestamp() * 0.001
        if item.metadata.confidence:
            base += item.metadata.confidence
        return base

    def _pick_preferred(self, left: MemoryItem, right: MemoryItem) -> MemoryItem:
        return left if self._recency_score(left) >= self._recency_score(right) else right

    def _contradicts(self, left: str, right: str) -> bool:
        left_l = left.lower()
        right_l = right.lower()
        negations = (
            "not ", "no longer ", "don't ", "do not ", "doesn't ",
            "isn't ", "never ", "stopped ", "switched from ", "used to ",
        )
        left_negated = any(neg in left_l for neg in negations)
        right_negated = any(neg in right_l for neg in negations)
        if left_negated == right_negated:
            return False
        ignored = {
            "not", "no", "longer", "do", "dont", "doesnt", "isnt", "never",
            "stopped", "switched", "from", "used", "to",
        }
        left_terms = {
            term.rstrip("s")
            for term in re.findall(r"[a-z0-9]+", left_l)
            if term not in ignored
        }
        right_terms = {
            term.rstrip("s")
            for term in re.findall(r"[a-z0-9]+", right_l)
            if term not in ignored
        }
        overlap = len(left_terms & right_terms) / max(len(left_terms | right_terms), 1)
        if overlap >= 0.6:
            return True

        # Catch common preference/stack changes where the negated sentence
        # uses a different value (for example, "uses Postgres" vs
        # "switched to SQLite") but shares the same decision subject.
        context_pattern = r"\b(?:uses?|using|prefer(?:s|red)?|chosen|selected)\b"
        left_context = re.split(context_pattern, left_l, maxsplit=1)[0].strip()
        right_context = re.split(context_pattern, right_l, maxsplit=1)[0].strip()
        return bool(left_context and left_context == right_context)
