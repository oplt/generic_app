from __future__ import annotations

import asyncio

from backend.core.config import settings
from backend.lib.vectors import estimate_tokens
from backend.modules.rag.domain.models import DocumentChunk, ParsedDocument
from backend.modules.rag.infrastructure.langchain_text_splitters import split_documents
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException


def prefix_suffix_overlap(previous: str, current: str) -> int:
    """Return the longest k where ``previous`` ends with ``current[:k]``.

    Uses Knuth–Morris–Pratt longest-prefix-suffix computation so adjacent chunk
    overlap metadata is linear in the combined string lengths instead of a
    nested backwards scan.
    """

    if not previous or not current:
        return 0
    max_len = min(len(previous), len(current))
    # Unique separator keeps the LPS border from crossing the chunk boundary.
    probe = f"{current[:max_len]}\0{previous[-max_len:]}"
    lps = [0] * len(probe)
    length = 0
    index = 1
    while index < len(probe):
        if probe[index] == probe[length]:
            length += 1
            lps[index] = length
            index += 1
        elif length:
            length = lps[length - 1]
        else:
            lps[index] = 0
            index += 1
    return min(lps[-1], max_len)


def _split_documents_with_token_counts(
    documents: list[ParsedDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
    tokenizer_model: str | None = None,
    document_aware: bool = False,
) -> list[tuple[str, int, dict]]:
    return [
        (content, estimate_tokens(content, model=tokenizer_model), meta)
        for content, meta in split_documents(
            documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer_model=tokenizer_model,
            document_aware=document_aware,
        )
    ]


def _child_windows(
    content: str,
    *,
    parent_index: int,
    child_size: int,
    child_overlap: int,
    tokenizer_model: str | None,
) -> list[tuple[str, int]]:
    if child_size < 1:
        return []
    tokens = content.split()
    if not tokens:
        return [(content, estimate_tokens(content, model=tokenizer_model))]
    # Approximate token windows via whitespace tokens for deterministic children.
    step = max(1, child_size - child_overlap)
    windows: list[tuple[str, int]] = []
    for start in range(0, len(tokens), step):
        piece = " ".join(tokens[start : start + child_size]).strip()
        if not piece:
            continue
        windows.append((piece, estimate_tokens(piece, model=tokenizer_model)))
        if start + child_size >= len(tokens):
            break
    if not windows:
        windows.append((content, estimate_tokens(content, model=tokenizer_model)))
    _ = parent_index
    return windows


class ChunkingService:
    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig.from_settings()

    async def chunk(
        self,
        documents: list[ParsedDocument],
        *,
        document_id: str,
        user_id: str,
        filename: str,
        project_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[DocumentChunk]:
        document_aware = bool(getattr(self.config, "document_aware_chunking", False))
        pieces = await asyncio.to_thread(
            _split_documents_with_token_counts,
            documents,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            tokenizer_model=getattr(self.config, "embedding_model", None),
            document_aware=document_aware,
        )
        parent_child = bool(getattr(self.config, "parent_child_chunking", False))
        child_size = int(getattr(self.config, "parent_child_child_size", 200) or 200)
        child_overlap = int(getattr(self.config, "parent_child_child_overlap", 40) or 40)

        parents: list[tuple[str, int, dict]] = []
        previous_content = ""
        for index, (content, token_count, meta) in enumerate(pieces):
            overlap_chars = prefix_suffix_overlap(previous_content, content)
            section_path = meta.get("section_path") or meta.get("section_heading")
            parents.append(
                (
                    content,
                    token_count,
                    {
                        **meta,
                        "document_id": document_id,
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "project_id": project_id,
                        "filename": filename,
                        "chunk_index": index,
                        "chunk_char_count": len(content),
                        "chunk_token_count": token_count,
                        "format": meta.get("format", "unknown"),
                        "section_heading": meta.get("section_heading"),
                        "section_path": section_path,
                        "overlap_char_count": overlap_chars,
                        "page_number": meta.get("page_number"),
                        "source_type": "upload",
                        "chunk_role": "parent" if parent_child else "chunk",
                        "document_aware_chunking": document_aware,
                    },
                )
            )
            previous_content = content

        # Wire previous/next relationships on parent/base chunks.
        for index, (_, _, meta) in enumerate(parents):
            meta["prev_chunk_index"] = index - 1 if index > 0 else None
            meta["next_chunk_index"] = index + 1 if index + 1 < len(parents) else None
            meta["chunk_count"] = len(parents)

        chunks: list[DocumentChunk] = []
        if not parent_child:
            for index, (content, token_count, meta) in enumerate(parents):
                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        user_id=user_id,
                        chunk_index=index,
                        content=content,
                        token_count=token_count,
                        organization_id=organization_id,
                        project_id=project_id,
                        metadata={
                            "source_metadata": {
                                key: value
                                for key, value in meta.items()
                                if key
                                not in {
                                    "document_id",
                                    "user_id",
                                    "organization_id",
                                    "project_id",
                                }
                            },
                            **meta,
                        },
                    )
                )
        else:
            # Index children for ANN; keep parent text for optional expansion.
            child_index = 0
            for parent_index, (parent_content, parent_tokens, parent_meta) in enumerate(parents):
                windows = _child_windows(
                    parent_content,
                    parent_index=parent_index,
                    child_size=child_size,
                    child_overlap=child_overlap,
                    tokenizer_model=getattr(self.config, "embedding_model", None),
                )
                for window_offset, (child_content, child_tokens) in enumerate(windows):
                    chunks.append(
                        DocumentChunk(
                            document_id=document_id,
                            user_id=user_id,
                            chunk_index=child_index,
                            content=child_content,
                            token_count=child_tokens,
                            organization_id=organization_id,
                            project_id=project_id,
                            metadata={
                                **parent_meta,
                                "chunk_index": child_index,
                                "chunk_role": "child",
                                "parent_chunk_index": parent_index,
                                "parent_content": parent_content,
                                "parent_token_count": parent_tokens,
                                "child_offset": window_offset,
                                "chunk_token_count": child_tokens,
                                "chunk_char_count": len(child_content),
                                "chunk_count": None,  # filled below
                            },
                        )
                    )
                    child_index += 1
            for chunk in chunks:
                chunk.metadata["chunk_count"] = len(chunks)
                parent_idx = chunk.metadata.get("parent_chunk_index")
                chunk.metadata["prev_chunk_index"] = (
                    chunk.chunk_index - 1 if chunk.chunk_index > 0 else None
                )
                chunk.metadata["next_chunk_index"] = (
                    chunk.chunk_index + 1 if chunk.chunk_index + 1 < len(chunks) else None
                )
                chunk.metadata["parent_prev_chunk_index"] = (
                    parent_idx - 1 if isinstance(parent_idx, int) and parent_idx > 0 else None
                )
                chunk.metadata["parent_next_chunk_index"] = (
                    parent_idx + 1
                    if isinstance(parent_idx, int) and parent_idx + 1 < len(parents)
                    else None
                )

        if len(chunks) > settings.RAG_MAX_DOCUMENT_CHUNKS:
            raise HTTPException(
                status_code=413,
                detail="Document produces more chunks than the configured limit.",
            )
        return chunks
