"""Optional generation-quality heuristics (no mandatory LLM-as-judge)."""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")
_CITATION_PATTERN = re.compile(r"\[(?:source|citation)\s*#?\s*(\d+)\]", re.I)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def heuristic_generation_scores(
    *,
    query: str,
    answer: str,
    context_chunks: list[str],
    expected_facts: list[str] | None = None,
) -> dict[str, float]:
    """Cheap, deterministic generation hooks for the workbench.

    Expensive LLM-as-judge execution is intentionally not required.
    """

    context = "\n".join(context_chunks)
    answer_tokens = _tokens(answer)
    context_tokens = _tokens(context)
    query_tokens = _tokens(query)
    if not answer_tokens:
        return {
            "groundedness": 0.0,
            "citation_correctness": 0.0,
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
        }

    groundedness = len(answer_tokens & context_tokens) / len(answer_tokens)
    citations = [int(match) for match in _CITATION_PATTERN.findall(answer)]
    citation_correctness = (
        sum(1 for index in citations if 1 <= index <= len(context_chunks)) / len(citations)
        if citations
        else (1.0 if context_chunks else 0.0)
    )
    faithfulness = groundedness
    if expected_facts:
        fact_hits = sum(1 for fact in expected_facts if fact.lower() in answer.lower())
        faithfulness = (faithfulness + fact_hits / len(expected_facts)) / 2
    answer_relevance = (
        len(answer_tokens & query_tokens) / len(query_tokens) if query_tokens else 0.0
    )
    return {
        "groundedness": round(groundedness, 6),
        "citation_correctness": round(citation_correctness, 6),
        "faithfulness": round(faithfulness, 6),
        "answer_relevance": round(answer_relevance, 6),
    }
