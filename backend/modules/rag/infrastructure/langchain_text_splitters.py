from __future__ import annotations

from backend.modules.rag.domain.models import ParsedDocument


def split_documents(
    documents: list[ParsedDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[tuple[str, dict]]:
    """Split parsed documents using LangChain RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    results: list[tuple[str, dict]] = []
    for doc in documents:
        pieces = splitter.split_text(doc.content)
        for piece in pieces:
            metadata = {**doc.metadata}
            if doc.page_number is not None:
                metadata.setdefault("page_number", doc.page_number)
            results.append((piece, metadata))
    return results
