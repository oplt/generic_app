from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.pagination import DEFAULT_PAGE_LIMIT
from backend.modules.ai import metrics
from backend.modules.ai.application.rag_answer_prompt import resolve_rag_answer_prompt
from backend.modules.ai.budgets import validate_context_budget, validate_prompt_budget
from backend.modules.ai.document_service import AiDocumentService
from backend.modules.ai.models import AiPromptVersion, AiRun
from backend.modules.ai.prompt_service import AiPromptService, _render_template
from backend.modules.ai.providers import ProviderGenerateRequest
from backend.modules.identity_access.models import User
from backend.modules.rag.application.prompt_context_service import PromptContextService
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.observability.instruments import set_current_span_attributes


class AiRunService(AiPromptService, AiDocumentService):
    async def run_prompt(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
        variables: dict[str, Any],
        retrieval_query: str | None,
        document_ids: list[str],
        top_k: int,
        review_required: bool,
        evaluation_dataset_id: str | None = None,
        evaluation_case_id: str | None = None,
        additional_system_context: str | None = None,
        retrieved_chunk_ids: list[str] | None = None,
        retrieval_degraded: bool = False,
        memory_degraded: bool = False,
        degradation_reason: str | None = None,
        injection_chunks_filtered: int = 0,
    ):
        template, version = await self._resolve_prompt_version(
            user,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
        )
        matches: list[dict[str, Any]] = []
        resolved_chunk_ids = list(retrieved_chunk_ids or [])
        rag_config = RagConfig.from_settings()
        if retrieval_query and rag_config.enabled:
            context = await PromptContextService(self.db, rag_config=rag_config).build(
                query=retrieval_query,
                user_id=user.id,
                agent_id="default",
                run_id=None,
                project_id=None,
                document_ids=document_ids or None,
                top_k=top_k,
            )
            validate_context_budget(context.document_context)
            variables = {**variables, "retrieval_context": context.document_context}
            resolved_chunk_ids = context.retrieved_chunk_ids
            retrieval_degraded = context.retrieval_degraded
            memory_degraded = context.memory_degraded
            degradation_reason = context.degradation_reason
            injection_chunks_filtered = context.injection_chunks_filtered
            additional_system_context = self._merge_system_context(
                additional_system_context,
                context.system_context,
            )
        elif retrieval_query:
            matches = await self.retrieve_chunks(
                user,
                query=retrieval_query,
                document_ids=document_ids,
                top_k=top_k,
            )
            variables = {
                **variables,
                "retrieval_context": "\n\n".join(
                    f"[{item['document_title']} #{item['chunk_index']}]\n{item['content']}"
                    for item in matches
                ),
            }
            validate_context_budget(variables["retrieval_context"])
            resolved_chunk_ids = [item["chunk_id"] for item in matches]

        rendered_system_prompt = _render_template(version.system_prompt, variables)
        if additional_system_context:
            rendered_system_prompt = (
                f"{rendered_system_prompt.rstrip()}\n\n{additional_system_context}"
            )
        rendered_user_prompt = _render_template(version.user_prompt_template, variables)
        validate_prompt_budget(rendered_system_prompt, rendered_user_prompt)
        run = await self.repo.create_run(
            user_id=user.id,
            prompt_template_id=template.id if template else None,
            prompt_version_id=version.id,
            evaluation_dataset_id=evaluation_dataset_id,
            evaluation_case_id=evaluation_case_id,
            provider_key=version.provider_key,
            model_name=version.model_name,
            status="running",
            response_format=version.response_format,
            variables_json=variables,
            retrieval_query=retrieval_query,
            retrieved_chunk_ids_json=resolved_chunk_ids,
            retrieval_degraded=retrieval_degraded,
            memory_degraded=memory_degraded,
            degradation_reason=degradation_reason,
            injection_chunks_filtered=injection_chunks_filtered,
            input_messages_json=[
                {"role": "system", "content": rendered_system_prompt},
                {"role": "user", "content": rendered_user_prompt},
            ],
            review_status="pending" if review_required else "not_requested",
        )

        await self.db.flush()
        return await self._finalize_run_generation(
            user=user,
            run=run,
            version=version,
            rendered_system_prompt=rendered_system_prompt,
            rendered_user_prompt=rendered_user_prompt,
            review_required=review_required,
        )

    @staticmethod
    def _merge_system_context(*blocks: str | None) -> str | None:
        merged = [block.strip() for block in blocks if block and block.strip()]
        return "\n\n".join(merged) or None

    async def run_rag_answer(
        self,
        user: User,
        *,
        query: str,
        combined_context: str,
        retrieved_chunk_ids: list[str],
        review_required: bool = False,
        retrieval_degraded: bool = False,
        memory_degraded: bool = False,
        degradation_reason: str | None = None,
        injection_chunks_filtered: int = 0,
    ) -> AiRun:
        prompt_spec = await resolve_rag_answer_prompt(self.repo, user)

        reference_context = combined_context.strip()
        validate_context_budget(reference_context)
        rendered_system_prompt = (
            f"{prompt_spec.system_prompt}\n\n{reference_context}"
            if reference_context
            else prompt_spec.system_prompt
        )
        rendered_user_prompt = query
        validate_prompt_budget(rendered_system_prompt, rendered_user_prompt)

        run = await self.repo.create_run(
            user_id=user.id,
            prompt_template_id=prompt_spec.template_id,
            prompt_version_id=prompt_spec.version_id,
            provider_key=prompt_spec.provider_key,
            model_name=prompt_spec.model_name,
            status="running",
            response_format=prompt_spec.response_format,
            variables_json={"query": query},
            retrieval_query=query,
            retrieved_chunk_ids_json=retrieved_chunk_ids,
            retrieval_degraded=retrieval_degraded,
            memory_degraded=memory_degraded,
            degradation_reason=degradation_reason,
            injection_chunks_filtered=injection_chunks_filtered,
            input_messages_json=[
                {"role": "system", "content": rendered_system_prompt},
                {"role": "user", "content": rendered_user_prompt},
            ],
            review_status="pending" if review_required else "not_requested",
        )
        await self.db.flush()
        return await self._finalize_run_generation(
            user=user,
            run=run,
            version=prompt_spec.execution_version,
            rendered_system_prompt=rendered_system_prompt,
            rendered_user_prompt=rendered_user_prompt,
            review_required=review_required,
        )

    async def _finalize_run_generation(
        self,
        *,
        user: User,
        run: AiRun,
        version: AiPromptVersion | SimpleNamespace,
        rendered_system_prompt: str,
        rendered_user_prompt: str,
        review_required: bool,
    ) -> AiRun:
        provider = self.providers.get(run.provider_key)
        set_current_span_attributes(
            module="ai",
            provider=run.provider_key,
            model=run.model_name,
            job_id=run.id,
        )
        started = perf_counter()
        run.provider_attempts = 0
        run.provider_retry_count = 0
        run.provider_last_status_code = None
        run.provider_last_error = None
        run.provider_deadline_at = datetime.now(UTC) + timedelta(
            seconds=settings.AI_REQUEST_TIMEOUT_SECONDS
        )
        try:
            result = await asyncio.wait_for(
                provider.generate(
                    ProviderGenerateRequest(
                        model=version.model_name,
                        system_prompt=rendered_system_prompt,
                        user_prompt=rendered_user_prompt,
                        response_format=version.response_format,
                        temperature=version.temperature,
                        idempotency_key=f"ai-run:{run.id}",
                    )
                ),
                timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
            )
            latency_ms = int((perf_counter() - started) * 1000)
            metrics.ai_run_latency_ms.observe(latency_ms)
            run.status = "completed"
            run.output_text = result.output_text
            run.output_json = result.output_json
            run.latency_ms = latency_ms
            run.input_tokens = result.input_tokens
            run.output_tokens = result.output_tokens
            run.total_tokens = result.total_tokens
            run.provider_attempts = result.attempts
            run.provider_retry_count = result.retries
            run.provider_last_status_code = result.last_status_code
            set_current_span_attributes(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                provider_attempts=result.attempts,
                provider_retry_count=result.retries,
            )
            run.estimated_cost_micros = (result.input_tokens * version.input_cost_per_million) + (
                result.output_tokens * version.output_cost_per_million
            )
            run.completed_at = datetime.now(UTC)
        except TimeoutError as exc:
            metrics.ai_run_failed_total.inc()
            self._record_provider_failure(run, exc)
            run.status = "failed"
            run.error_message = "AI provider execution timed out"
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise HTTPException(status_code=504, detail="AI provider execution timed out") from exc
        except HTTPException as exc:
            metrics.ai_run_failed_total.inc()
            self._record_provider_failure(run, exc)
            run.status = "failed"
            run.error_message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise
        except Exception as exc:
            metrics.ai_run_failed_total.inc()
            self._record_provider_failure(run, exc)
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise HTTPException(status_code=502, detail="AI provider execution failed") from exc

        if review_required:
            await self.repo.create_review(
                run_id=run.id,
                requested_by_user_id=user.id,
                status="pending",
            )

        await self.db.commit()
        await self.db.refresh(run)
        return run

    @staticmethod
    def _record_provider_failure(run: AiRun, error: Exception) -> None:
        metadata = getattr(error, "metadata", None)
        if metadata is not None:
            run.provider_attempts = max(1, int(metadata.attempts))
            run.provider_retry_count = max(0, int(metadata.retries))
            run.provider_last_status_code = metadata.last_status_code
        elif not getattr(run, "provider_attempts", 0):
            run.provider_attempts = 1
        run.provider_last_error = str(error)[:500]

    async def list_runs(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_runs_for_user(user.id, limit=limit, offset=offset)
