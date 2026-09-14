from __future__ import annotations

import asyncio

from backend.core.config import settings
from backend.lib.vectors import decode_tokens, encode_text, estimate_tokens
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
    child_size: int,
    child_overlap: int,
    tokenizer_model: str | None,
) -> list[dict]:
    """Tokenizer-aligned child windows (same estimate/encode abstraction as parents)."""

    if child_size < 1 or not content:
        return []

    token_ids = encode_text(content, model=tokenizer_model)
    windows: list[dict] = []
    if token_ids is not None:
        step = max(1, child_size - child_overlap)
        for start in range(0, len(token_ids), step):
            piece_ids = token_ids[start : start + child_size]
            if not piece_ids:
                continue
            piece = decode_tokens(piece_ids, model=tokenizer_model) or ""
            if not piece.strip():
                continue
            # Approximate char span via progressive decode for metadata only.
            prefix = decode_tokens(token_ids[:start], model=tokenizer_model) or ""
            char_start = len(prefix)
            char_end = char_start + len(piece)
            windows.append(
                {
                    "content": piece,
                    "token_count": len(piece_ids),
                    "token_start": start,
                    "token_end": start + len(piece_ids),
                    "char_start": char_start,
                    "char_end": char_end,
                }
            )
            if start + child_size >= len(token_ids):
                break
    else:
        # Fallback: same RecursiveCharacterTextSplitter length_function as parents.
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_size,
            chunk_overlap=child_overlap,
            length_function=lambda value: estimate_tokens(value, model=tokenizer_model),
        )
        search_from = 0
        for piece in splitter.split_text(content):
            if not piece.strip():
                continue
            idx = content.find(piece, search_from)
            if idx < 0:
                idx = search_from
            char_start = idx
            char_end = idx + len(piece)
            token_start = estimate_tokens(content[:char_start], model=tokenizer_model) - 1
            token_start = max(0, token_start) if char_start else 0
            token_count = estimate_tokens(piece, model=tokenizer_model)
            windows.append(
                {
                    "content": piece,
                    "token_count": token_count,
                    "token_start": token_start,
                    "token_end": token_start + token_count,
                    "char_start": char_start,
                    "char_end": char_end,
                }
            )
            search_from = char_end

    if not windows:
        token_count = estimate_tokens(content, model=tokenizer_model)
        windows.append(
            {
                "content": content,
                "token_count": token_count,
                "token_start": 0,
                "token_end": token_count,
                "char_start": 0,
                "char_end": len(content),
            }
        )
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
            # Persist parents as reference rows (no ANN embedding) and children
            # for retrieval. Do not duplicate full parent text on every child.
            tokenizer_model = getattr(self.config, "embedding_model", None)
            for parent_index, (parent_content, parent_tokens, parent_meta) in enumerate(parents):
                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        user_id=user_id,
                        chunk_index=parent_index,
                        content=parent_content,
                        token_count=parent_tokens,
                        organization_id=organization_id,
                        project_id=project_id,
                        metadata={
                            **parent_meta,
                            "chunk_index": parent_index,
                            "chunk_role": "parent",
                            "chunk_token_count": parent_tokens,
                            "chunk_char_count": len(parent_content),
                        },
                    )
                )

            child_index = len(parents)
            for parent_index, (parent_content, parent_tokens, parent_meta) in enumerate(parents):
                windows = _child_windows(
                    parent_content,
                    child_size=child_size,
                    child_overlap=child_overlap,
                    tokenizer_model=tokenizer_model,
                )
                for window_offset, window in enumerate(windows):
                    chunks.append(
                        DocumentChunk(
                            document_id=document_id,
                            user_id=user_id,
                            chunk_index=child_index,
                            content=window["content"],
                            token_count=int(window["token_count"]),
                            organization_id=organization_id,
                            project_id=project_id,
                            metadata={
                                **{
                                    key: value
                                    for key, value in parent_meta.items()
                                    if key
                                    not in {
                                        "chunk_role",
                                        "chunk_index",
                                        "chunk_token_count",
                                        "chunk_char_count",
                                        "overlap_char_count",
                                    }
                                },
                                "chunk_index": child_index,
                                "chunk_role": "child",
                                "parent_chunk_index": parent_index,
                                "parent_token_count": parent_tokens,
                                "child_offset": window_offset,
                                "token_start": window["token_start"],
                                "token_end": window["token_end"],
                                "char_start": window["char_start"],
                                "char_end": window["char_end"],
                                "chunk_token_count": window["token_count"],
                                "chunk_char_count": len(window["content"]),
                                "section_path": parent_meta.get("section_path"),
                                "page_number": parent_meta.get("page_number"),
                            },
                        )
                    )
                    child_index += 1
            for chunk in chunks:
                chunk.metadata["chunk_count"] = len(chunks)
                if chunk.metadata.get("chunk_role") == "child":
                    parent_idx = chunk.metadata.get("parent_chunk_index")
                    chunk.metadata["prev_chunk_index"] = (
                        chunk.chunk_index - 1 if chunk.chunk_index > 0 else None
                    )
                    chunk.metadata["next_chunk_index"] = (
                        chunk.chunk_index + 1
                        if chunk.chunk_index + 1 < len(chunks)
                        else None
                    )
                    chunk.metadata["parent_prev_chunk_index"] = (
                        parent_idx - 1
                        if isinstance(parent_idx, int) and parent_idx > 0
                        else None
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
