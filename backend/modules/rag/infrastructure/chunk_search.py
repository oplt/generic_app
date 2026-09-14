"""Bounded vector and lexical candidate generation for RAG retrieval."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.lib.vector_search import (
    embedding_is_indexable,
    pgvector_readiness,
    reset_pgvector_readiness_cache,
)
from backend.lib.vectors import vector_literal
from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.infrastructure.pgvector_errors import PgVectorUnavailableError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _scope_filters(
    *,
    user_id: str,
    project_id: str | None,
    document_ids: list[str] | None,
    source_type: str | None,
    organization_id: str | None,
) -> tuple[list[str], dict[str, Any]]:
    filters = [
        (
            "(c.user_id = :user_id OR c.organization_id = :organization_id)"
            if organization_id is not None
            else "c.user_id = :user_id"
        ),
        "d.status = 'indexed'",
        "d.deleted_at IS NULL",
    ]
    params: dict[str, Any] = {"user_id": user_id}
    if organization_id is not None:
        params["organization_id"] = organization_id
        filters.append("c.organization_id = :organization_id")
    if project_id:
        filters.append("c.project_id = :project_id")
        params["project_id"] = project_id
    if document_ids:
        filters.append("c.document_id = ANY(:document_ids)")
        params["document_ids"] = document_ids
    if source_type:
        filters.append("d.source_type = :source_type")
        params["source_type"] = source_type
    return filters, params


def _rows_to_chunks(rows) -> list[RetrievedChunk]:
    retrieved: list[RetrievedChunk] = []
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        retrieved.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                score=round(float(row["score"]), 4),
                filename=row["original_filename"],
                chunk_index=row["chunk_index"],
                page_number=meta.get("page_number"),
                metadata={
                    **meta,
                    "lexical_score": float(row.get("lexical_score") or 0.0),
                    "retrieval_lane": row.get("retrieval_lane"),
                },
            )
        )
    return retrieved


async def similarity_search_indexed(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    document_ids: list[str] | None,
    source_type: str | None,
    query: str,
    query_embedding: list[float],
    top_k: int,
    score_threshold: float,
    candidate_limit: int | None = None,
    organization_id: str | None = None,
) -> list[RetrievedChunk]:
    readiness = await pgvector_readiness(db)
    if not readiness.available:
        raise PgVectorUnavailableError(readiness.reason or "readiness_check_failed")
    if not embedding_is_indexable(query_embedding):
        raise PgVectorUnavailableError("query_dimension_mismatch")

    filters, params = _scope_filters(
        user_id=user_id,
        project_id=project_id,
        document_ids=document_ids,
        source_type=source_type,
        organization_id=organization_id,
    )
    filters.extend(
        [
            "c.embedding IS NOT NULL",
            "(1 - (c.embedding <=> CAST(:query_vec AS vector))) >= :score_threshold",
        ]
    )
    params.update(
        {
            "query_vec": vector_literal(query_embedding),
            "score_threshold": score_threshold,
            "candidate_limit": max(top_k, candidate_limit or top_k),
        }
    )
    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.content,
            c.chunk_index,
            c.metadata_json,
            d.original_filename,
            (1 - (c.embedding <=> CAST(:query_vec AS vector))) AS score,
            0.0 AS lexical_score,
            'vector' AS retrieval_lane
        FROM rag_chunks c
        INNER JOIN rag_documents d ON d.id = c.document_id
        WHERE {" AND ".join(filters)}
        ORDER BY c.embedding <=> CAST(:query_vec AS vector)
        LIMIT :candidate_limit
    """
    # Tune hnsw.ef_search / iterative_scan only from docs/runbooks/filtered-hnsw-recall.md
    # and only via SET LOCAL inside the retrieval transaction—never session-wide.
    try:
        result = await db.execute(text(sql), params)
    except Exception as exc:
        logger.exception("Indexed pgvector search failed")
        reset_pgvector_readiness_cache()
        raise PgVectorUnavailableError("query_failed") from exc
    return _rows_to_chunks(result.mappings().all())


async def lexical_search_indexed(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    document_ids: list[str] | None,
    source_type: str | None,
    query: str,
    candidate_limit: int,
    organization_id: str | None = None,
) -> list[RetrievedChunk]:
    """Independent FTS lane ordered by lexical rank, not vector distance."""

    cleaned = (query or "").strip()
    if not cleaned or candidate_limit < 1:
        return []

    filters, params = _scope_filters(
        user_id=user_id,
        project_id=project_id,
        document_ids=document_ids,
        source_type=source_type,
        organization_id=organization_id,
    )
    filters.append("c.content_tsv @@ plainto_tsquery('simple', :search_query)")
    params.update(
        {
            "search_query": cleaned,
            "candidate_limit": candidate_limit,
        }
    )
    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.content,
            c.chunk_index,
            c.metadata_json,
            d.original_filename,
            ts_rank_cd(
                c.content_tsv,
                plainto_tsquery('simple', :search_query)
            ) AS score,
            ts_rank_cd(
                c.content_tsv,
                plainto_tsquery('simple', :search_query)
            ) AS lexical_score,
            'lexical' AS retrieval_lane
        FROM rag_chunks c
        INNER JOIN rag_documents d ON d.id = c.document_id
        WHERE {" AND ".join(filters)}
        ORDER BY score DESC, c.id ASC
        LIMIT :candidate_limit
    """
    try:
        result = await db.execute(text(sql), params)
    except Exception:
        logger.exception("Indexed lexical search failed")
        return []
    return _rows_to_chunks(result.mappings().all())
