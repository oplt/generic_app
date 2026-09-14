from __future__ import annotations

import re
from dataclasses import dataclass

from backend.modules.rag.domain.models import Citation, RetrievedChunk

_SOURCE_PATTERN = re.compile(r"\[(?:source|citation)\s*#?\s*(\d+)\]", re.I)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")


@dataclass(frozen=True, slots=True)
class CitationValidation:
    valid: bool
    cited_chunk_ids: frozenset[str]
    invalid_references: int
    groundedness: float


class CitationService:
    def build_citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                filename=chunk.filename,
                score=chunk.score,
                snippet=chunk.content[:400],
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
            )
            for chunk in chunks
        ]

    def validate_answer(
        self,
        answer: str | None,
        chunks: list[RetrievedChunk],
        *,
        threshold: float = 0.35,
    ) -> CitationValidation:
        text = answer or ""
        cited_ids = {chunk.chunk_id for chunk in chunks if chunk.chunk_id in text}
        source_matches = [int(value) for value in _SOURCE_PATTERN.findall(text)]
        invalid = sum(1 for index in source_matches if index < 1 or index > len(chunks))
        cited_ids.update(
            chunks[index - 1].chunk_id
            for index in source_matches
            if 1 <= index <= len(chunks)
        )

        context_tokens = set(
            _TOKEN_PATTERN.findall(" ".join(chunk.content for chunk in chunks).lower())
        )
        sentences = [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]
        sentence_scores = []
        for sentence in sentences:
            sentence_tokens = set(_TOKEN_PATTERN.findall(sentence.lower()))
            sentence_scores.append(
                len(sentence_tokens & context_tokens) / max(len(sentence_tokens), 1)
            )
        groundedness = sum(score >= threshold for score in sentence_scores) / max(
            len(sentence_scores), 1
        )
        has_explicit_citation = bool(source_matches or cited_ids)
        return CitationValidation(
            valid=(
                invalid == 0
                and (not has_explicit_citation or bool(cited_ids))
                and groundedness >= threshold
            ),
            cited_chunk_ids=frozenset(cited_ids),
            invalid_references=invalid,
            groundedness=round(groundedness, 4),
        )
