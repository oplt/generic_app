"""RAG evaluation workbench: probe, dataset runs, compare, export."""

from __future__ import annotations

import csv
import io
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.lib.concurrency import bounded_gather
from backend.lib.vectors import can_index_embedding
from backend.modules.rag.application.candidate_expansion import resolve_candidate_plan
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.evaluation_repository import RagEvaluationRepository
from backend.modules.rag.application.rag_context_builder import RagContextBuilder
from backend.modules.rag.application.retrieval_ranker import (
    HybridRetrievalRanker,
    reciprocal_rank_fuse,
)
from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.evaluation.judges import heuristic_generation_scores
from backend.modules.rag.evaluation.metrics import (
    judgments_from_expected,
    metric_deltas,
    retrieval_metrics,
)
from backend.modules.rag.infrastructure.models import (
    RagEvaluationCase,
    RagEvaluationDataset,
    RagEvaluationRun,
)
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.infrastructure.vector_store_adapter import build_vector_store
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "golden_v1.json"


class RagEvaluationService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.repo = RagEvaluationRepository(db)
        self.rag_repo = RagRepository(db)
        self.vector_store = build_vector_store(db, self.config)
        self.embeddings = EmbeddingService(self.config)
        self.ranker = HybridRetrievalRanker()
        self.context_builder = RagContextBuilder()

    async def list_datasets(
        self, *, user_id: str, organization_id: str | None
    ) -> tuple[list[RagEvaluationDataset], int]:
        return await self.repo.list_datasets(user_id=user_id, organization_id=organization_id)

    async def create_dataset(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> RagEvaluationDataset:
        return await self.repo.create_dataset(
            user_id=user_id,
            organization_id=organization_id,
            name=name.strip(),
            description=description,
            tags_json=list(tags or []),
        )

    async def get_dataset(
        self, dataset_id: str, *, user_id: str, organization_id: str | None
    ) -> RagEvaluationDataset:
        dataset = await self.repo.get_dataset(
            dataset_id, user_id=user_id, organization_id=organization_id
        )
        if dataset is None:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        return dataset

    async def list_cases(
        self, dataset_id: str, *, user_id: str, organization_id: str | None
    ) -> list[RagEvaluationCase]:
        await self.get_dataset(dataset_id, user_id=user_id, organization_id=organization_id)
        return await self.repo.list_cases(dataset_id)

    async def create_case(
        self,
        dataset_id: str,
        *,
        user_id: str,
        organization_id: str | None,
        question: str,
        expected_document_ids: list[str] | None = None,
        expected_chunk_ids: list[str] | None = None,
        expected_sources: list[str] | None = None,
        expected_facts: list[str] | None = None,
        judgments: dict[str, int] | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> RagEvaluationCase:
        await self.get_dataset(dataset_id, user_id=user_id, organization_id=organization_id)
        return await self.repo.create_case(
            dataset_id=dataset_id,
            question=question.strip(),
            expected_document_ids_json=list(expected_document_ids or []),
            expected_chunk_ids_json=list(expected_chunk_ids or []),
            expected_sources_json=list(expected_sources or []),
            expected_facts_json=list(expected_facts or []),
            judgments_json=dict(judgments or {}),
            tags_json=list(tags or []),
            notes=notes,
        )

    async def import_golden_dataset(
        self, *, user_id: str, organization_id: str | None
    ) -> RagEvaluationDataset:
        payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        dataset = await self.create_dataset(
            user_id=user_id,
            organization_id=organization_id,
            name=payload.get("dataset_id", "golden-v1"),
            description=payload.get("description"),
            tags=["golden", "offline"],
        )
        for case in payload.get("queries", []):
            judgments = {
                str(chunk_id): int(grade)
                for chunk_id, grade in (case.get("judgments") or {}).items()
            }
            await self.repo.create_case(
                dataset_id=dataset.id,
                question=case["query"],
                expected_document_ids_json=[],
                expected_chunk_ids_json=[
                    chunk_id for chunk_id, grade in judgments.items() if grade > 0
                ],
                expected_sources_json=[],
                expected_facts_json=[],
                judgments_json=judgments,
                tags_json=list(case.get("tags") or []),
                notes=case.get("id"),
            )
        return dataset

    async def probe(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        query: str,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        strategy: str | None = None,
        top_k: int | None = None,
        include_generation_judges: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        result = await self._retrieve_detailed(
            query=query,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
            document_ids=document_ids,
            strategy=strategy,
            top_k=top_k,
        )
        generation_scores = None
        generation_ms = 0.0
        answer = None
        if include_generation_judges and result["candidates"]:
            gen_started = perf_counter()
            answer = f"{result['candidates'][0]['content']} [Source 1]"
            generation_scores = heuristic_generation_scores(
                query=query,
                answer=answer,
                context_chunks=[item["content"] for item in result["context_chunks"]],
            )
            generation_ms = (perf_counter() - gen_started) * 1000
        result["latencies_ms"]["generation"] = round(generation_ms, 3)
        result["latencies_ms"]["total"] = round((perf_counter() - started) * 1000, 3)
        result["generation"] = {
            "answer": answer,
            "scores": generation_scores,
            "provider": "heuristic" if include_generation_judges else None,
        }
        return result

    async def run_dataset(
        self,
        dataset_id: str,
        *,
        user_id: str,
        organization_id: str | None,
        name: str = "run",
        project_id: str | None = None,
        strategy: str | None = None,
        top_k: int | None = None,
        baseline_run_id: str | None = None,
        include_generation_judges: bool = False,
    ) -> RagEvaluationRun:
        dataset = await self.get_dataset(
            dataset_id, user_id=user_id, organization_id=organization_id
        )
        cases = await self.repo.list_cases(dataset.id)
        if not cases:
            raise HTTPException(status_code=400, detail="Dataset has no evaluation cases")

        baseline = None
        if baseline_run_id:
            baseline = await self.repo.get_run(
                baseline_run_id, user_id=user_id, organization_id=organization_id
            )
            if baseline is None:
                raise HTTPException(status_code=404, detail="Baseline run not found")

        configuration = {
            "strategy": strategy or self.config.retrieval_strategy,
            "top_k": top_k or self.config.top_k,
            "project_id": project_id,
            "include_generation_judges": include_generation_judges,
            "rrf_k": self.config.rrf_k,
            "rerank_enabled": self.config.rerank_enabled,
            "reranker_backend": getattr(self.config, "reranker_backend", "lightweight"),
            "quality": {
                "dedup_exact": getattr(self.config, "dedup_exact_enabled", False),
                "dedup_near": getattr(self.config, "dedup_near_enabled", False),
                "mmr": getattr(self.config, "mmr_enabled", False),
                "neighbor_expansion": getattr(
                    self.config, "neighbor_expansion_enabled", False
                ),
                "parent_child_retrieval": getattr(
                    self.config, "parent_child_retrieval_enabled", False
                ),
                "per_document_limit": getattr(self.config, "per_document_limit", 0),
            },
        }
        try:
            from backend.modules.rag.application.index_version_service import (
                IndexVersionService,
            )
            from backend.modules.rag.application.pipeline_versions import (
                pipeline_snapshot_from_row,
            )

            active = await IndexVersionService(self.db, config=self.config).ensure_active_version()
            snapshot = pipeline_snapshot_from_row(active)
            configuration["index_version"] = active.key
            configuration["pipeline"] = {
                "parser_version": snapshot.get("parser_version"),
                "chunker_version": snapshot.get("chunker_version"),
                "embedding_schema_version": snapshot.get("embedding_schema_version"),
                "embedding_provider": snapshot.get("embedding_provider"),
                "embedding_model": snapshot.get("embedding_model"),
                "embedding_dimensions": snapshot.get("embedding_dimensions"),
            }
        except Exception:
            configuration["index_version"] = None
        run = await self.repo.create_run(
            dataset_id=dataset.id,
            user_id=user_id,
            organization_id=organization_id,
            name=name.strip() or "run",
            status="running",
            configuration_json=configuration,
            metrics_json={},
            latency_json={},
            baseline_run_id=baseline_run_id,
        )
        # Commit before remote embedding / retrieval so the DB lease is not held
        # across external I/O (transaction ownership).
        await self.db.commit()
        await self.db.refresh(run)

        case_metrics: list[dict[str, float]] = []
        latency_samples: dict[str, list[float]] = {
            key: []
            for key in (
                "embedding",
                "vector",
                "lexical",
                "fusion",
                "rerank",
                "context",
                "generation",
                "total",
            )
        }
        try:
            for case in cases:
                detailed = await self._retrieve_detailed(
                    query=case.question,
                    user_id=user_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    document_ids=None,
                    strategy=strategy,
                    top_k=top_k,
                )
                ranked_ids = [item["chunk_id"] for item in detailed["candidates"]]
                judgments = judgments_from_expected(
                    expected_chunk_ids=list(case.expected_chunk_ids_json or []),
                    judgments={
                        str(k): int(v) for k, v in (case.judgments_json or {}).items()
                    },
                )
                metrics = retrieval_metrics(
                    ranked_ids, judgments, configuration["top_k"]
                )
                generation_scores = {}
                if include_generation_judges and detailed["candidates"]:
                    answer = f"{detailed['candidates'][0]['content']} [Source 1]"
                    generation_scores = heuristic_generation_scores(
                        query=case.question,
                        answer=answer,
                        context_chunks=[c["content"] for c in detailed["context_chunks"]],
                        expected_facts=list(case.expected_facts_json or []),
                    )
                    metrics = {**metrics, **generation_scores}
                case_metrics.append(metrics)
                for key, value in detailed["latencies_ms"].items():
                    latency_samples.setdefault(key, []).append(float(value))
                await self.repo.create_run_item(
                    run_id=run.id,
                    case_id=case.id,
                    ranked_chunk_ids_json=ranked_ids,
                    candidates_json=detailed["candidates"],
                    metrics_json=metrics,
                    latency_json=detailed["latencies_ms"],
                    included_in_context=True,
                    notes=None,
                    score=float(metrics.get("ndcg_at_k", 0.0)),
                )
                await self.db.commit()

            aggregate = {
                key: round(statistics.fmean(item[key] for item in case_metrics), 6)
                for key in case_metrics[0]
            }
            latency_summary = {
                key: {
                    "mean": round(statistics.fmean(values), 3),
                    "p50": round(statistics.median(values), 3),
                }
                for key, values in latency_samples.items()
                if values
            }
            comparison = None
            if baseline is not None:
                comparison = {
                    "baseline_run_id": baseline.id,
                    "deltas": metric_deltas(baseline.metrics_json or {}, aggregate),
                }
            run.status = "completed"
            run.metrics_json = aggregate
            run.latency_json = latency_summary
            run.comparison_json = comparison
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.commit()
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.commit()
            raise

    async def get_run(
        self, run_id: str, *, user_id: str, organization_id: str | None
    ) -> tuple[RagEvaluationRun, list]:
        run = await self.repo.get_run(
            run_id, user_id=user_id, organization_id=organization_id
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        items = await self.repo.list_run_items(run.id)
        return run, items

    async def list_runs(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        dataset_id: str | None = None,
    ) -> tuple[list[RagEvaluationRun], int]:
        if dataset_id:
            await self.get_dataset(
                dataset_id, user_id=user_id, organization_id=organization_id
            )
        return await self.repo.list_runs(
            user_id=user_id,
            organization_id=organization_id,
            dataset_id=dataset_id,
        )

    async def export_run(
        self,
        run_id: str,
        *,
        user_id: str,
        organization_id: str | None,
        fmt: str = "json",
    ) -> tuple[str, str, str]:
        run, items = await self.get_run(
            run_id, user_id=user_id, organization_id=organization_id
        )
        payload = {
            "run": {
                "id": run.id,
                "dataset_id": run.dataset_id,
                "name": run.name,
                "status": run.status,
                "configuration": run.configuration_json,
                "metrics": run.metrics_json,
                "latency": run.latency_json,
                "comparison": run.comparison_json,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
            "items": [
                {
                    "case_id": item.case_id,
                    "ranked_chunk_ids": item.ranked_chunk_ids_json,
                    "metrics": item.metrics_json,
                    "latency": item.latency_json,
                    "score": item.score,
                }
                for item in items
            ],
        }
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "case_id",
                    "score",
                    "recall_at_k",
                    "precision_at_k",
                    "mrr",
                    "ndcg_at_k",
                    "ranked_chunk_ids",
                ],
            )
            writer.writeheader()
            for item in items:
                metrics = item.metrics_json or {}
                writer.writerow(
                    {
                        "case_id": item.case_id,
                        "score": item.score,
                        "recall_at_k": metrics.get("recall_at_k"),
                        "precision_at_k": metrics.get("precision_at_k"),
                        "mrr": metrics.get("mrr"),
                        "ndcg_at_k": metrics.get("ndcg_at_k"),
                        "ranked_chunk_ids": "|".join(item.ranked_chunk_ids_json or []),
                    }
                )
            return buffer.getvalue(), "text/csv", f"rag-eval-{run.id}.csv"
        return (
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            "application/json",
            f"rag-eval-{run.id}.json",
        )

    async def _retrieve_detailed(
        self,
        *,
        query: str,
        user_id: str,
        organization_id: str | None,
        project_id: str | None,
        document_ids: list[str] | None,
        strategy: str | None,
        top_k: int | None,
    ) -> dict[str, Any]:
        resolved_top_k = top_k or self.config.top_k
        plan = resolve_candidate_plan(self.config, top_k=resolved_top_k, strategy=strategy)
        filters: dict[str, Any] = {}
        from backend.modules.rag.application.index_version_service import IndexVersionService

        active = await IndexVersionService(self.db, config=self.config).get_active_version()
        if active is not None:
            filters["index_version_id"] = active.id
        if document_ids:
            valid = await self.rag_repo.filter_document_ids_for_user(
                user_id,
                list(dict.fromkeys(document_ids)),
                project_id=project_id,
                organization_id=organization_id,
            )
            if not valid:
                return {
                    "strategy": plan.strategy,
                    "candidates": [],
                    "context_chunks": [],
                    "assembled_context": "",
                    "latencies_ms": {
                        "embedding": 0.0,
                        "vector": 0.0,
                        "lexical": 0.0,
                        "fusion": 0.0,
                        "rerank": 0.0,
                        "context": 0.0,
                    },
                }
            filters["document_ids"] = valid

        latencies = {
            "embedding": 0.0,
            "vector": 0.0,
            "lexical": 0.0,
            "fusion": 0.0,
            "rerank": 0.0,
            "context": 0.0,
        }
        query_embedding: list[float] | None = None
        if plan.needs_embedding:
            embed_started = perf_counter()
            query_embedding = (await self.embeddings.embed_texts([query]))[0]
            latencies["embedding"] = round((perf_counter() - embed_started) * 1000, 3)
            if not can_index_embedding(
                query_embedding, expected_dimensions=self.config.embedding_dimensions
            ):
                raise HTTPException(status_code=503, detail="embedding_dimension_mismatch")

        vector_chunks: list[RetrievedChunk] = []
        lexical_chunks: list[RetrievedChunk] = []

        async def _vector() -> list[RetrievedChunk]:
            assert query_embedding is not None
            return await self.vector_store.similarity_search(
                query,
                user_id=user_id,
                project_id=project_id,
                top_k=plan.vector_limit,
                filters=filters,
                query_embedding=query_embedding,
                organization_id=organization_id,
            )

        async def _lexical() -> list[RetrievedChunk]:
            return await self.rag_repo.lexical_search_indexed(
                user_id=user_id,
                project_id=project_id,
                document_ids=filters.get("document_ids"),
                source_type=None,
                query=query,
                candidate_limit=plan.lexical_limit,
                organization_id=organization_id,
                index_version_id=filters.get("index_version_id"),
            )

        if plan.strategy == "vector":
            started = perf_counter()
            vector_chunks = await _vector()
            latencies["vector"] = round((perf_counter() - started) * 1000, 3)
            fused = vector_chunks
        elif plan.strategy == "lexical":
            started = perf_counter()
            lexical_chunks = await _lexical()
            latencies["lexical"] = round((perf_counter() - started) * 1000, 3)
            fused = lexical_chunks
        else:
            vector_started = perf_counter()
            lexical_started = perf_counter()
            vector_result, lexical_result = await bounded_gather(
                [_vector(), _lexical()],
                limit=2,
                return_exceptions=True,
                kind="rag_eval_probe",
            )
            if isinstance(vector_result, BaseException):
                raise vector_result
            vector_chunks = list(vector_result)
            latencies["vector"] = round((perf_counter() - vector_started) * 1000, 3)
            if isinstance(lexical_result, BaseException):
                lexical_chunks = []
            else:
                lexical_chunks = list(lexical_result)
            latencies["lexical"] = round((perf_counter() - lexical_started) * 1000, 3)
            fuse_started = perf_counter()
            fused = (
                reciprocal_rank_fuse(
                    [vector_chunks, lexical_chunks],
                    limit=plan.fuse_limit,
                    k=plan.rrf_k,
                )
                if lexical_chunks
                else vector_chunks[: plan.fuse_limit]
            )
            latencies["fusion"] = round((perf_counter() - fuse_started) * 1000, 3)

        vector_ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(vector_chunks, start=1)}
        lexical_ranks = {
            chunk.chunk_id: rank for rank, chunk in enumerate(lexical_chunks, start=1)
        }

        rerank_scores: dict[str, float] = {}
        if plan.post_rerank:
            rerank_started = perf_counter()
            ranked = self.ranker.rerank(query, fused, limit=plan.final_top_k)
            latencies["rerank"] = round((perf_counter() - rerank_started) * 1000, 3)
            # Approximate reranker score from position for display.
            for index, chunk in enumerate(ranked):
                rerank_scores[chunk.chunk_id] = round(1.0 / (index + 1), 6)
        else:
            ranked = fused[: plan.final_top_k]

        context_started = perf_counter()
        context_chunks = self.context_builder.trim_chunks_to_token_budget(
            ranked, max_tokens=self.config.max_context_tokens
        )
        assembled = self.context_builder.build_document_context_block(context_chunks)
        latencies["context"] = round((perf_counter() - context_started) * 1000, 3)
        included_ids = {chunk.chunk_id for chunk in context_chunks}

        vector_scores = {chunk.chunk_id: chunk.score for chunk in vector_chunks}
        lexical_scores = {
            chunk.chunk_id: float(chunk.metadata.get("lexical_score") or chunk.score)
            for chunk in lexical_chunks
        }

        candidates = [
            {
                "rank": rank,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section": chunk.metadata.get("section") or chunk.metadata.get("section_path"),
                "content": chunk.content,
                "vector_rank": vector_ranks.get(chunk.chunk_id),
                "lexical_rank": lexical_ranks.get(chunk.chunk_id),
                "vector_score": vector_scores.get(chunk.chunk_id),
                "lexical_score": lexical_scores.get(chunk.chunk_id),
                "fused_score": chunk.metadata.get("rrf_score"),
                "reranker_score": rerank_scores.get(chunk.chunk_id),
                "included": chunk.chunk_id in included_ids,
                "metadata": dict(chunk.metadata),
            }
            for rank, chunk in enumerate(ranked, start=1)
        ]
        return {
            "strategy": plan.strategy,
            "top_k": plan.final_top_k,
            "candidates": candidates,
            "context_chunks": [
                item for item in candidates if item["chunk_id"] in included_ids
            ],
            "assembled_context": assembled,
            "latencies_ms": latencies,
        }
