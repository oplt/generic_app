from __future__ import annotations

from backend.lib.vectors import estimate_tokens
from backend.modules.rag.domain.models import ParsedDocument

# Prefer splitting on structure before falling back to whitespace/characters.
_DOCUMENT_AWARE_SEPARATORS = (
    "\n## ",
    "\n### ",
    "\n#### ",
    "\n\n",
    "\n- ",
    "\n* ",
    "\n1. ",
    "\n",
    ". ",
    " ",
    "",
)


def split_documents(
    documents: list[ParsedDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
    tokenizer_model: str | None = None,
    document_aware: bool = False,
) -> list[tuple[str, dict]]:
    """Split parsed documents using LangChain RecursiveCharacterTextSplitter.

    CPU-bound: call only via ``asyncio.to_thread`` (see ``ChunkingService.chunk``).

    ``chunk_size`` / ``chunk_overlap`` are interpreted as token estimates (len/4),
    aligned with ``RagContextBuilder.trim_chunks_to_token_budget``.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter_kwargs: dict = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "length_function": lambda value: estimate_tokens(value, model=tokenizer_model),
    }
    if document_aware:
        splitter_kwargs["separators"] = list(_DOCUMENT_AWARE_SEPARATORS)
    splitter = RecursiveCharacterTextSplitter(**splitter_kwargs)
    results: list[tuple[str, dict]] = []
    for doc in documents:
        pieces = splitter.split_text(doc.content)
        section_heading = doc.metadata.get("section_heading")
        section_path = doc.metadata.get("section_path") or section_heading
        for piece in pieces:
            metadata = {**doc.metadata}
            if doc.page_number is not None:
                metadata.setdefault("page_number", doc.page_number)
            if section_path:
                metadata.setdefault("section_path", section_path)
            if section_heading:
                metadata.setdefault("section_heading", section_heading)
            results.append((piece, metadata))
    return results
