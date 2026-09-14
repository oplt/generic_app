"""Measure filtered HNSW Recall@K against exact distance search.

Builds a skewed multi-tenant corpus, compares:

1. production filtered SQL (whatever plan PostgreSQL chooses),
2. exact filtered distance ordering (indexscans disabled),
3. unfiltered HNSW over-fetch then post-filter (classic ANN+filter failure mode),

captures EXPLAIN (ANALYZE, BUFFERS), and sweeps only transaction-local knobs
supported by the deployed pgvector version. Never SET without LOCAL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.lib.vectors import vector_literal
from backend.modules.rag.infrastructure.chunk_search import _scope_filters
from backend.modules.rag.infrastructure.models import RAG_VECTOR_DIMENSIONS

FILTER_TYPES = ("user", "organization", "project", "document", "source")
DEFAULT_EF_SEARCH_CANDIDATES = (None, 40, 100, 200)
DEFAULT_CANDIDATE_MULTIPLIERS = (1, 3, 10)
FIXTURE_PREFIX = "fhr"


@dataclass(frozen=True, slots=True)
class FilterScenario:
    name: str
    user_id: str
    organization_id: str | None
    project_id: str | None
    document_ids: list[str] | None
    source_type: str | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_ids: list[str]
    latency_ms: float
    plan_text: str | None = None


def unit_vector(*, primary: float, seed: int, jitter: float = 0.0) -> list[float]:
    """Build a deterministic unit vector with controllable alignment on axis 0."""

    rng = random.Random(seed)
    values = [jitter * (rng.random() - 0.5) for _ in range(RAG_VECTOR_DIMENSIONS)]
    values[0] = primary
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def recall_at_k(exact_ids: list[str], ann_ids: list[str], k: int) -> float:
    """Fraction of exact top-k ids recovered by the ANN result set."""

    truth = exact_ids[:k]
    if not truth:
        return 1.0
    recovered = set(ann_ids).intersection(truth)
    return len(recovered) / len(truth)


def parse_pgvector_version(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    parts: list[int] = []
    for token in raw.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def supports_iterative_scan(pgvector_version: tuple[int, ...]) -> bool:
    # iterative_scan landed in pgvector 0.7.0.
    return bool(pgvector_version) and pgvector_version >= (0, 7, 0)


def plan_uses_embedding_hnsw(plan_text: str | None) -> bool:
    if not plan_text:
        return False
    lowered = plan_text.lower()
    return (
        "ix_rag_chunks_embedding_hnsw" in lowered
        or "using hnsw" in lowered
        or "index scan using hnsw" in lowered
    )


def classify_plan(plan_text: str | None) -> str:
    if plan_uses_embedding_hnsw(plan_text):
        return "embedding_hnsw"
    if not plan_text:
        return "unknown"
    lowered = plan_text.lower()
    if "sort" in lowered and ("index scan" in lowered or "seq scan" in lowered):
        return "filter_then_sort"
    if "seq scan" in lowered:
        return "seq_scan"
    return "other"


async def probe_runtime(db: AsyncSession) -> dict[str, Any]:
    pg_version = await db.scalar(text("SHOW server_version"))
    pgvector_version = await db.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    )
    version_tuple = parse_pgvector_version(
        str(pgvector_version) if pgvector_version is not None else None
    )
    ef_search_probe: str | None = None
    ef_search_supported = False
    try:
        await db.execute(text("SET LOCAL hnsw.ef_search = 40"))
        ef_search_probe = await db.scalar(text("SHOW hnsw.ef_search"))
        ef_search_supported = True
    except Exception:
        ef_search_supported = False

    iterative_supported = False
    iterative_modes: list[str] = []
    if supports_iterative_scan(version_tuple):
        for mode in ("off", "relaxed_order", "strict_order"):
            try:
                await db.execute(text(f"SET LOCAL hnsw.iterative_scan = {mode}"))
                iterative_supported = True
                iterative_modes.append(mode)
            except Exception:
                continue

    index_def = await db.scalar(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'rag_chunks'
              AND indexname = 'ix_rag_chunks_embedding_hnsw'
            """
        )
    )
    return {
        "postgresql_version": pg_version,
        "pgvector_version": pgvector_version,
        "pgvector_version_tuple": list(version_tuple),
        "hnsw_ef_search_supported": ef_search_supported,
        "hnsw_ef_search_probe": ef_search_probe,
        "hnsw_iterative_scan_supported": iterative_supported,
        "hnsw_iterative_scan_modes": iterative_modes,
        "hnsw_indexdef": index_def,
        "vector_dimensions": RAG_VECTOR_DIMENSIONS,
    }


def _search_sql(*, filters: list[str], explain: bool) -> str:
    prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " if explain else ""
    return f"""
        {prefix}
        SELECT
            c.id AS chunk_id,
            (1 - (c.embedding <=> CAST(:query_vec AS vector))) AS score
        FROM rag_chunks c
        INNER JOIN rag_documents d ON d.id = c.document_id
        WHERE {" AND ".join(filters)}
        ORDER BY c.embedding <=> CAST(:query_vec AS vector)
        LIMIT :candidate_limit
    """


def _postfilter_sql(*, filters: list[str], explain: bool) -> str:
    """Unfiltered HNSW/ANN over-fetch, then apply tenant filters (failure-mode probe)."""

    prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " if explain else ""
    return f"""
        {prefix}
        WITH ann AS (
            SELECT
                c.id,
                c.document_id,
                c.user_id,
                c.organization_id,
                c.project_id,
                c.embedding,
                c.content,
                c.chunk_index,
                c.metadata_json
            FROM rag_chunks c
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:query_vec AS vector)
            LIMIT :overfetch
        )
        SELECT
            ann.id AS chunk_id,
            (1 - (ann.embedding <=> CAST(:query_vec AS vector))) AS score
        FROM ann
        INNER JOIN rag_documents d ON d.id = ann.document_id
        WHERE {" AND ".join(filters).replace("c.", "ann.")}
        ORDER BY ann.embedding <=> CAST(:query_vec AS vector)
        LIMIT :candidate_limit
    """


async def _apply_local_knobs(
    db: AsyncSession,
    *,
    exact: bool,
    ef_search: int | None,
    iterative_scan: str | None,
) -> None:
    if exact:
        await db.execute(text("SET LOCAL enable_indexscan = off"))
        await db.execute(text("SET LOCAL enable_bitmapscan = off"))
    if ef_search is not None:
        await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
    if iterative_scan is not None:
        await db.execute(text(f"SET LOCAL hnsw.iterative_scan = {iterative_scan}"))


async def _run_search(
    db: AsyncSession,
    *,
    scenario: FilterScenario,
    query_embedding: list[float],
    top_k: int,
    candidate_limit: int,
    score_threshold: float,
    exact: bool,
    ef_search: int | None,
    iterative_scan: str | None,
    explain: bool,
    mode: str = "production",
    overfetch: int | None = None,
) -> SearchResult:
    filters, params = _scope_filters(
        user_id=scenario.user_id,
        project_id=scenario.project_id,
        document_ids=scenario.document_ids,
        source_type=scenario.source_type,
        organization_id=scenario.organization_id,
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
            "candidate_limit": max(top_k, candidate_limit),
        }
    )
    if mode == "postfilter":
        params["overfetch"] = max(overfetch or candidate_limit, candidate_limit)
        # Post-filter CTE already requires embedding IS NOT NULL on the ANN stage.
        filters = [item for item in filters if "embedding IS NOT NULL" not in item]
        sql = _postfilter_sql(filters=filters, explain=explain)
    else:
        sql = _search_sql(filters=filters, explain=explain)

    await _apply_local_knobs(
        db,
        exact=exact,
        ef_search=ef_search,
        iterative_scan=iterative_scan,
    )

    started = time.perf_counter()
    result = await db.execute(text(sql), params)
    latency_ms = (time.perf_counter() - started) * 1000.0
    if explain:
        plan_lines = [str(row[0]) for row in result.fetchall()]
        return SearchResult(chunk_ids=[], latency_ms=latency_ms, plan_text="\n".join(plan_lines))

    chunk_ids = [str(row["chunk_id"]) for row in result.mappings().all()]
    return SearchResult(chunk_ids=chunk_ids, latency_ms=latency_ms)


async def _ensure_fixture_parents(
    db: AsyncSession,
    *,
    run_id: str,
    target_user_id: str,
    noise_user_id: str,
    organization_id: str,
    noise_organization_id: str,
    project_id: str,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO users (
              id, email, password_hash, is_active, is_admin, is_verified, mfa_enabled, created_at
            )
            VALUES
              (:target_user, :target_email, 'fhr-bench', true, false, true, false, NOW()),
              (:noise_user, :noise_email, 'fhr-bench', true, false, true, false, NOW())
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "target_user": target_user_id,
            "noise_user": noise_user_id,
            "target_email": f"{FIXTURE_PREFIX}-target-{run_id}@example.com",
            "noise_email": f"{FIXTURE_PREFIX}-noise-{run_id}@example.com",
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO organizations (id, name, created_at)
            VALUES
              (:org, :org_name, NOW()),
              (:noise_org, :noise_org_name, NOW())
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "org": organization_id,
            "noise_org": noise_organization_id,
            "org_name": f"{FIXTURE_PREFIX}-org-{run_id}",
            "noise_org_name": f"{FIXTURE_PREFIX}-noise-org-{run_id}",
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO projects (id, owner_id, name, created_at)
            VALUES (:project_id, :owner_id, :name, NOW())
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "project_id": project_id,
            "owner_id": target_user_id,
            "name": f"{FIXTURE_PREFIX}-project-{run_id}",
        },
    )


async def build_skewed_fixture(
    db: AsyncSession,
    *,
    run_id: str,
    noise_chunks: int,
    target_relevant: int,
    target_filler: int,
) -> dict[str, Any]:
    """Insert a corpus where unfiltered ANN prefers noise over filtered truth."""

    target_user_id = f"{FIXTURE_PREFIX}-user-{run_id}"
    noise_user_id = f"{FIXTURE_PREFIX}-noise-user-{run_id}"
    organization_id = f"{FIXTURE_PREFIX}-org-{run_id}"
    noise_organization_id = f"{FIXTURE_PREFIX}-noise-org-{run_id}"
    project_id = f"{FIXTURE_PREFIX}-project-{run_id}"
    target_document_id = f"{FIXTURE_PREFIX}-doc-{run_id}"
    noise_document_id = f"{FIXTURE_PREFIX}-noise-doc-{run_id}"
    source_document_id = f"{FIXTURE_PREFIX}-source-doc-{run_id}"

    await _ensure_fixture_parents(
        db,
        run_id=run_id,
        target_user_id=target_user_id,
        noise_user_id=noise_user_id,
        organization_id=organization_id,
        noise_organization_id=noise_organization_id,
        project_id=project_id,
    )

    await db.execute(
        text(
            """
            INSERT INTO rag_documents (
              id, user_id, organization_id, project_id, filename, original_filename,
              content_type, content_fingerprint, status, source_type, metadata_json,
              created_at, updated_at
            ) VALUES
              (
                :target_doc, :target_user, :org, :project, 'target.txt', 'target.txt',
                'text/plain', :fp1, 'indexed', 'upload', '{}', NOW(), NOW()
              ),
              (
                :noise_doc, :noise_user, :noise_org, NULL, 'noise.txt', 'noise.txt',
                'text/plain', :fp2, 'indexed', 'upload', '{}', NOW(), NOW()
              ),
              (
                :source_doc, :target_user, :org, :project, 'chat.txt', 'chat.txt',
                'text/plain', :fp3, 'indexed', 'chat', '{}', NOW(), NOW()
              )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "target_doc": target_document_id,
            "noise_doc": noise_document_id,
            "source_doc": source_document_id,
            "target_user": target_user_id,
            "noise_user": noise_user_id,
            "org": organization_id,
            "noise_org": noise_organization_id,
            "project": project_id,
            "fp1": f"fp-target-{run_id}",
            "fp2": f"fp-noise-{run_id}",
            "fp3": f"fp-source-{run_id}",
        },
    )

    query_embedding = unit_vector(primary=1.0, seed=1, jitter=0.0)
    rows: list[dict[str, Any]] = []

    for index in range(noise_chunks):
        rows.append(
            {
                "id": f"{FIXTURE_PREFIX}-noise-{run_id}-{index}",
                "document_id": noise_document_id,
                "user_id": noise_user_id,
                "organization_id": noise_organization_id,
                "project_id": None,
                "chunk_index": index,
                "content": f"noise chunk {index}",
                "embedding": vector_literal(
                    unit_vector(primary=0.99, seed=10_000 + index, jitter=0.01)
                ),
            }
        )

    relevant_ids: list[str] = []
    for index in range(target_relevant):
        chunk_id = f"{FIXTURE_PREFIX}-relevant-{run_id}-{index}"
        relevant_ids.append(chunk_id)
        rows.append(
            {
                "id": chunk_id,
                "document_id": target_document_id,
                "user_id": target_user_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "chunk_index": index,
                "content": f"relevant target chunk {index}",
                "embedding": vector_literal(
                    unit_vector(primary=0.90 - (index * 0.01), seed=20_000 + index, jitter=0.01)
                ),
            }
        )

    for index in range(target_filler):
        rows.append(
            {
                "id": f"{FIXTURE_PREFIX}-filler-{run_id}-{index}",
                "document_id": target_document_id,
                "user_id": target_user_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "chunk_index": target_relevant + index,
                "content": f"filler target chunk {index}",
                "embedding": vector_literal(
                    unit_vector(primary=0.20, seed=30_000 + index, jitter=0.05)
                ),
            }
        )

    for index in range(max(3, target_relevant)):
        rows.append(
            {
                "id": f"{FIXTURE_PREFIX}-chat-{run_id}-{index}",
                "document_id": source_document_id,
                "user_id": target_user_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "chunk_index": index,
                "content": f"chat source chunk {index}",
                "embedding": vector_literal(
                    unit_vector(primary=0.88 - (index * 0.01), seed=40_000 + index, jitter=0.01)
                ),
            }
        )

    insert_sql = text(
        """
        INSERT INTO rag_chunks (
          id, document_id, user_id, organization_id, project_id, chunk_index,
          content, token_count, metadata_json, embedding, created_at, updated_at
        ) VALUES (
          :id, :document_id, :user_id, :organization_id, :project_id, :chunk_index,
          :content, 8, '{}', CAST(:embedding AS vector), NOW(), NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    batch_size = 100
    for offset in range(0, len(rows), batch_size):
        await db.execute(insert_sql, rows[offset : offset + batch_size])

    await db.commit()
    return {
        "run_id": run_id,
        "query_embedding": query_embedding,
        "relevant_ids": relevant_ids,
        "counts": {
            "noise_chunks": noise_chunks,
            "target_relevant": target_relevant,
            "target_filler": target_filler,
            "total_inserted": len(rows),
        },
        "scenarios": {
            "user": asdict(
                FilterScenario(
                    name="user",
                    user_id=target_user_id,
                    organization_id=None,
                    project_id=None,
                    document_ids=None,
                    source_type=None,
                )
            ),
            "organization": asdict(
                FilterScenario(
                    name="organization",
                    user_id=target_user_id,
                    organization_id=organization_id,
                    project_id=None,
                    document_ids=None,
                    source_type=None,
                )
            ),
            "project": asdict(
                FilterScenario(
                    name="project",
                    user_id=target_user_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    document_ids=None,
                    source_type=None,
                )
            ),
            "document": asdict(
                FilterScenario(
                    name="document",
                    user_id=target_user_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    document_ids=[target_document_id],
                    source_type=None,
                )
            ),
            "source": asdict(
                FilterScenario(
                    name="source",
                    user_id=target_user_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    document_ids=None,
                    source_type="chat",
                )
            ),
        },
    }


async def cleanup_fixture(db: AsyncSession, run_id: str) -> None:
    await db.execute(
        text("DELETE FROM rag_chunks WHERE id LIKE :prefix"),
        {"prefix": f"{FIXTURE_PREFIX}-%{run_id}%"},
    )
    await db.execute(
        text("DELETE FROM rag_documents WHERE id LIKE :prefix"),
        {"prefix": f"{FIXTURE_PREFIX}-%{run_id}%"},
    )
    await db.execute(
        text("DELETE FROM projects WHERE id LIKE :prefix"),
        {"prefix": f"{FIXTURE_PREFIX}-%{run_id}%"},
    )
    await db.execute(
        text("DELETE FROM organizations WHERE id LIKE :prefix"),
        {"prefix": f"{FIXTURE_PREFIX}-%{run_id}%"},
    )
    await db.execute(
        text("DELETE FROM users WHERE id LIKE :prefix OR email LIKE :email_prefix"),
        {
            "prefix": f"{FIXTURE_PREFIX}-%{run_id}%",
            "email_prefix": f"{FIXTURE_PREFIX}-%{run_id}%",
        },
    )
    await db.commit()


def _summarize_trial(
    *,
    exact: SearchResult,
    ann: SearchResult,
    plan: SearchResult,
    top_k: int,
    candidate_multiplier: int,
    ef_search: int | None,
    iterative_scan: str | None,
    mode: str,
) -> dict[str, Any]:
    plan_text = plan.plan_text
    return {
        "mode": mode,
        "candidate_multiplier": candidate_multiplier,
        "candidate_limit": top_k * candidate_multiplier,
        "ef_search": ef_search,
        "iterative_scan": iterative_scan,
        "returned": len(ann.chunk_ids),
        "recall_at_k": round(recall_at_k(exact.chunk_ids, ann.chunk_ids, top_k), 6),
        "ann_latency_ms": round(ann.latency_ms, 3),
        "exact_latency_ms": round(exact.latency_ms, 3),
        "plan_class": classify_plan(plan_text),
        "ann_uses_embedding_hnsw": plan_uses_embedding_hnsw(plan_text),
        "ann_plan": plan_text,
        "exact_chunk_ids": exact.chunk_ids,
        "ann_chunk_ids": ann.chunk_ids,
    }


async def measure_filter_scenario(
    db: AsyncSession,
    *,
    scenario: FilterScenario,
    query_embedding: list[float],
    top_k: int,
    score_threshold: float,
    ef_search_values: tuple[int | None, ...],
    candidate_multipliers: tuple[int, ...],
    iterative_modes: tuple[str | None, ...],
    runtime: dict[str, Any],
    postfilter_overfetch: int,
) -> dict[str, Any]:
    async with db.begin():
        exact = await _run_search(
            db,
            scenario=scenario,
            query_embedding=query_embedding,
            top_k=top_k,
            candidate_limit=top_k,
            score_threshold=score_threshold,
            exact=True,
            ef_search=None,
            iterative_scan=None,
            explain=False,
        )
    async with db.begin():
        exact_plan = await _run_search(
            db,
            scenario=scenario,
            query_embedding=query_embedding,
            top_k=top_k,
            candidate_limit=top_k,
            score_threshold=score_threshold,
            exact=True,
            ef_search=None,
            iterative_scan=None,
            explain=True,
        )

    trials: list[dict[str, Any]] = []
    for multiplier in candidate_multipliers:
        for ef_search in ef_search_values:
            if ef_search is not None and not runtime["hnsw_ef_search_supported"]:
                continue
            for iterative_scan in iterative_modes:
                if iterative_scan is not None and not runtime["hnsw_iterative_scan_supported"]:
                    continue
                async with db.begin():
                    ann = await _run_search(
                        db,
                        scenario=scenario,
                        query_embedding=query_embedding,
                        top_k=top_k,
                        candidate_limit=top_k * multiplier,
                        score_threshold=score_threshold,
                        exact=False,
                        ef_search=ef_search,
                        iterative_scan=iterative_scan,
                        explain=False,
                    )
                async with db.begin():
                    ann_plan = await _run_search(
                        db,
                        scenario=scenario,
                        query_embedding=query_embedding,
                        top_k=top_k,
                        candidate_limit=top_k * multiplier,
                        score_threshold=score_threshold,
                        exact=False,
                        ef_search=ef_search,
                        iterative_scan=iterative_scan,
                        explain=True,
                    )
                trials.append(
                    _summarize_trial(
                        exact=exact,
                        ann=ann,
                        plan=ann_plan,
                        top_k=top_k,
                        candidate_multiplier=multiplier,
                        ef_search=ef_search,
                        iterative_scan=iterative_scan,
                        mode="production",
                    )
                )

    # Classic failure mode: unfiltered ANN then filter.
    async with db.begin():
        postfilter = await _run_search(
            db,
            scenario=scenario,
            query_embedding=query_embedding,
            top_k=top_k,
            candidate_limit=top_k,
            score_threshold=score_threshold,
            exact=False,
            ef_search=None,
            iterative_scan=None,
            explain=False,
            mode="postfilter",
            overfetch=postfilter_overfetch,
        )
    async with db.begin():
        postfilter_plan = await _run_search(
            db,
            scenario=scenario,
            query_embedding=query_embedding,
            top_k=top_k,
            candidate_limit=top_k,
            score_threshold=score_threshold,
            exact=False,
            ef_search=None,
            iterative_scan=None,
            explain=True,
            mode="postfilter",
            overfetch=postfilter_overfetch,
        )
    postfilter_trial = _summarize_trial(
        exact=exact,
        ann=postfilter,
        plan=postfilter_plan,
        top_k=top_k,
        candidate_multiplier=1,
        ef_search=None,
        iterative_scan=None,
        mode="postfilter_ann",
    )
    postfilter_trial["overfetch"] = postfilter_overfetch
    trials.append(postfilter_trial)

    production_trials = [item for item in trials if item["mode"] == "production"]
    best = max(
        production_trials,
        key=lambda item: (item["recall_at_k"], -item["ann_latency_ms"]),
    )
    default = next(
        (
            item
            for item in production_trials
            if item["candidate_multiplier"] == 1
            and item["ef_search"] is None
            and item["iterative_scan"] is None
        ),
        production_trials[0] if production_trials else None,
    )
    return {
        "filter": scenario.name,
        "exact_top_k": exact.chunk_ids,
        "exact_latency_ms": round(exact.latency_ms, 3),
        "exact_plan_class": classify_plan(exact_plan.plan_text),
        "exact_plan": exact_plan.plan_text,
        "default_trial": default,
        "best_trial": best,
        "postfilter_trial": postfilter_trial,
        "trials": trials,
    }


def recommend_settings(results: list[dict[str, Any]], runtime: dict[str, Any]) -> dict[str, Any]:
    """Choose settings only when production plans need them for Recall@K."""

    defaults = [
        item["default_trial"]
        for item in results
        if item.get("default_trial") is not None
    ]
    default_mean = (
        sum(item["recall_at_k"] for item in defaults) / len(defaults) if defaults else 0.0
    )
    hnsw_plan_count = sum(1 for item in defaults if item.get("ann_uses_embedding_hnsw"))
    postfilter_mean = (
        sum(item["postfilter_trial"]["recall_at_k"] for item in results) / len(results)
        if results
        else 0.0
    )

    candidates: dict[tuple[Any, Any, Any], list[float]] = {}
    latencies: dict[tuple[Any, Any, Any], list[float]] = {}
    for result in results:
        for trial in result["trials"]:
            if trial["mode"] != "production":
                continue
            key = (
                trial["candidate_multiplier"],
                trial["ef_search"],
                trial["iterative_scan"],
            )
            candidates.setdefault(key, []).append(trial["recall_at_k"])
            latencies.setdefault(key, []).append(trial["ann_latency_ms"])

    ranked = []
    for key, recalls in candidates.items():
        mean_recall = sum(recalls) / len(recalls)
        mean_latency = sum(latencies[key]) / len(latencies[key])
        ranked.append(
            {
                "candidate_multiplier": key[0],
                "ef_search": key[1],
                "iterative_scan": key[2],
                "mean_recall_at_k": round(mean_recall, 6),
                "mean_ann_latency_ms": round(mean_latency, 3),
            }
        )
    ranked.sort(
        key=lambda item: (
            -item["mean_recall_at_k"],
            item["candidate_multiplier"],
            item["ef_search"] or 0,
            item["mean_ann_latency_ms"],
        )
    )
    chosen = ranked[0] if ranked else None
    if default_mean >= 0.999 and hnsw_plan_count == 0:
        rationale = (
            "Production filtered queries used filter-then-sort (not embedding HNSW) with "
            "Recall@K=1.0. Leave hnsw.ef_search unset; do not raise global GUCs. Re-run this "
            "benchmark when EXPLAIN shows Index Scan using ix_rag_chunks_embedding_hnsw."
        )
    elif chosen and chosen["ef_search"] is None and chosen["candidate_multiplier"] == 1:
        rationale = (
            "Default transaction settings already achieve the best measured mean Recall@K."
        )
    else:
        rationale = (
            "Prefer the lowest candidate multiplier / SET LOCAL hnsw.ef_search that restores "
            "mean filtered Recall@K. Never SET without LOCAL on pooled connections."
        )
    return {
        "default_mean_recall_at_k": round(default_mean, 6),
        "production_plans_using_embedding_hnsw": hnsw_plan_count,
        "postfilter_ann_mean_recall_at_k": round(postfilter_mean, 6),
        "chosen": chosen,
        "rationale": rationale,
        "iterative_scan_note": (
            "hnsw.iterative_scan is unavailable on this pgvector version; upgrade to >= 0.7 "
            "before evaluating iterative filtered scans."
            if not runtime.get("hnsw_iterative_scan_supported")
            else "iterative_scan modes were included in the sweep."
        ),
        "ranked": ranked,
    }


async def run_benchmark(
    *,
    top_k: int = 5,
    noise_chunks: int = 800,
    target_relevant: int = 5,
    target_filler: int = 20,
    score_threshold: float = 0.0,
    ef_search_values: tuple[int | None, ...] = DEFAULT_EF_SEARCH_CANDIDATES,
    candidate_multipliers: tuple[int, ...] = DEFAULT_CANDIDATE_MULTIPLIERS,
    postfilter_overfetch: int | None = None,
    keep_fixture: bool = False,
) -> dict[str, Any]:
    from backend.db.session import SessionLocal

    run_id = uuid4().hex[:10]
    overfetch = postfilter_overfetch or max(50, noise_chunks // 2)
    async with SessionLocal() as db:
        runtime = await probe_runtime(db)
        await db.rollback()

    iterative_modes: tuple[str | None, ...] = (None,)
    if runtime["hnsw_iterative_scan_supported"]:
        iterative_modes = (None, "relaxed_order")

    async with SessionLocal() as db:
        fixture = await build_skewed_fixture(
            db,
            run_id=run_id,
            noise_chunks=noise_chunks,
            target_relevant=target_relevant,
            target_filler=target_filler,
        )

    results: list[dict[str, Any]] = []
    try:
        async with SessionLocal() as db:
            for name in FILTER_TYPES:
                scenario = FilterScenario(**fixture["scenarios"][name])
                results.append(
                    await measure_filter_scenario(
                        db,
                        scenario=scenario,
                        query_embedding=fixture["query_embedding"],
                        top_k=top_k,
                        score_threshold=score_threshold,
                        ef_search_values=ef_search_values,
                        candidate_multipliers=candidate_multipliers,
                        iterative_modes=iterative_modes,
                        runtime=runtime,
                        postfilter_overfetch=overfetch,
                    )
                )
    finally:
        if not keep_fixture:
            async with SessionLocal() as db:
                await cleanup_fixture(db, run_id)

    recommendation = recommend_settings(results, runtime)
    return {
        "benchmark": "filtered-hnsw-recall-v1",
        "top_k": top_k,
        "score_threshold": score_threshold,
        "runtime": runtime,
        "fixture": {
            "run_id": run_id,
            "counts": fixture["counts"],
            "postfilter_overfetch": overfetch,
            "kept": keep_fixture,
        },
        "filters": results,
        "recommendation": recommendation,
    }


def format_report(report: dict[str, Any]) -> str:
    runtime = report["runtime"]
    lines = [
        "Filtered HNSW Recall@K benchmark",
        f"PostgreSQL: {runtime.get('postgresql_version')}",
        f"pgvector: {runtime.get('pgvector_version')}",
        f"ef_search supported: {runtime.get('hnsw_ef_search_supported')}",
        f"iterative_scan supported: {runtime.get('hnsw_iterative_scan_supported')}",
        "",
    ]
    for result in report["filters"]:
        default = result.get("default_trial") or {}
        best = result.get("best_trial") or {}
        post = result.get("postfilter_trial") or {}
        lines.append(
            f"[{result['filter']}] production plan={default.get('plan_class')} "
            f"recall={default.get('recall_at_k')} "
            f"latency_ms={default.get('ann_latency_ms')} "
            f"| best recall={best.get('recall_at_k')} "
            f"mult={best.get('candidate_multiplier')} ef={best.get('ef_search')} "
            f"| postfilter recall={post.get('recall_at_k')} "
            f"returned={post.get('returned')}"
        )
    chosen = report["recommendation"].get("chosen") or {}
    lines.extend(
        [
            "",
            f"default mean Recall@{report['top_k']}="
            f"{report['recommendation'].get('default_mean_recall_at_k')}",
            "production plans using embedding HNSW="
            f"{report['recommendation'].get('production_plans_using_embedding_hnsw')}",
            "postfilter ANN mean Recall@"
            f"{report['top_k']}="
            f"{report['recommendation'].get('postfilter_ann_mean_recall_at_k')}",
            f"chosen: {chosen}",
            report["recommendation"].get("rationale", ""),
            report["recommendation"].get("iterative_scan_note", ""),
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--noise-chunks", type=int, default=800)
    parser.add_argument("--target-relevant", type=int, default=5)
    parser.add_argument("--target-filler", type=int, default=20)
    parser.add_argument("--score-threshold", type=float, default=0.0)
    parser.add_argument("--postfilter-overfetch", type=int, default=0)
    parser.add_argument("--keep-fixture", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)

    report = asyncio.run(
        run_benchmark(
            top_k=args.top_k,
            noise_chunks=args.noise_chunks,
            target_relevant=args.target_relevant,
            target_filler=args.target_filler,
            score_threshold=args.score_threshold,
            postfilter_overfetch=args.postfilter_overfetch or None,
            keep_fixture=args.keep_fixture,
        )
    )
    print(format_report(report))
    if args.json_output:
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
