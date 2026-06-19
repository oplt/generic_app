from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from backend.modules.ai.application.rag_answer_prompt import resolve_rag_answer_prompt
from backend.modules.ai.models import (
    AiEvaluationRun,
    AiPromptTemplate,
    AiPromptVersion,
    AiRun,
)
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.ai.repository import AiRepository
from backend.modules.ai.schemas import AiProviderDescriptor
from backend.modules.identity_access.models import User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.rag.application.legacy_ai_document_service import LegacyAiDocumentService

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


@dataclass(frozen=True, slots=True)
class _EvaluationCaseResult:
    case_id: str
    ai_run_id: str
    score: float
    passed: bool
    notes: str


def _render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    return PLACEHOLDER_PATTERN.sub(replace, template)


class AiService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AiRepository(db)
        self.providers = AiProviderRegistry()

    @staticmethod
    def list_provider_descriptors() -> list[AiProviderDescriptor]:
        return [
            AiProviderDescriptor(
                key="local",
                label="Local heuristic",
                supports_generation=True,
                supports_embeddings=True,
            ),
            AiProviderDescriptor(
                key="openai",
                label="OpenAI",
                supports_generation=True,
                supports_embeddings=True,
            ),
            AiProviderDescriptor(
                key="anthropic",
                label="Anthropic",
                supports_generation=True,
                supports_embeddings=settings.AI_EMBEDDING_PROVIDER == "anthropic",
            ),
        ]

    async def list_prompt_templates(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_prompt_templates_for_user(
            user.id, limit=limit, offset=offset
        )

    async def create_prompt_template(
        self, user: User, key: str, name: str, description: str | None
    ):
        existing = await self.repo.get_prompt_template_by_key_for_user(user.id, key)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A prompt template with this key already exists",
            )
        template = await self.repo.create_prompt_template(
            user_id=user.id,
            key=key,
            name=name,
            description=description,
        )
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_prompt_template(
        self, user: User, template_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        if "active_version_id" in updates and updates["active_version_id"]:
            version = await self.repo.get_prompt_version(updates["active_version_id"])
            if not version or version.prompt_template_id != template.id:
                raise HTTPException(
                    status_code=404,
                    detail="Prompt version not found for this template",
                )
            if not version.is_published:
                raise HTTPException(
                    status_code=422,
                    detail="Only published versions can be activated",
                )
        for field, value in updates.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def create_prompt_version(self, user: User, template_id: str, payload: dict[str, Any]):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions, _ = await self.repo.list_prompt_versions(template.id, limit=1, offset=0)
        next_version_number = (versions[0].version_number + 1) if versions else 1
        version = await self.repo.create_prompt_version(
            prompt_template_id=template.id,
            version_number=next_version_number,
            provider_key=payload["provider_key"],
            model_name=payload["model_name"],
            system_prompt=payload["system_prompt"],
            user_prompt_template=payload["user_prompt_template"],
            variable_definitions_json=[
                item.model_dump() for item in payload["variable_definitions"]
            ],
            response_format=payload["response_format"],
            temperature=payload["temperature"],
            rollout_percentage=payload["rollout_percentage"],
            is_published=payload["is_published"],
            input_cost_per_million=payload["input_cost_per_million"],
            output_cost_per_million=payload["output_cost_per_million"],
            created_by_user_id=user.id,
        )
        if template.active_version_id is None and version.is_published:
            template.active_version_id = version.id
        await self.db.commit()
        await self.db.refresh(version)
        await self.db.refresh(template)
        return version

    async def update_prompt_version(
        self, user: User, template_id: str, version_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        version = await self.repo.get_prompt_version(version_id)
        if not version or version.prompt_template_id != template.id:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        for field, value in updates.items():
            if field == "variable_definitions":
                version.variable_definitions_json = [item.model_dump() for item in value]
            else:
                setattr(version, field, value)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def list_prompt_versions(
        self,
        user: User,
        template_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        return await self.repo.list_prompt_versions(
            template.id, limit=limit, offset=offset
        )

    async def list_documents(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        self._require_rag_documents()
        return await LegacyAiDocumentService(self.db).list_documents(
            user.id, limit=limit, offset=offset
        )

    async def create_document_from_text(
        self,
        user: User,
        *,
        title: str,
        description: str | None,
        content: str,
        content_type: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        if not content.strip():
            raise HTTPException(status_code=422, detail="Document content must not be empty")
        max_bytes = settings.RAG_MAX_FILE_BYTES
        if len(content.encode("utf-8")) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Document exceeds the maximum size of {max_bytes} bytes",
            )
        self._require_rag_documents()
        return await LegacyAiDocumentService(self.db).create_from_text(
            user_id=user.id,
            title=title,
            description=description,
            content=content,
            content_type=content_type,
            filename=filename,
            metadata=metadata,
        )

    async def create_document_from_upload(
        self, user: User, file: UploadFile, description: str | None
    ):
        self._require_rag_documents()
        return await LegacyAiDocumentService(self.db).create_from_upload(
            user_id=user.id,
            file=file,
            description=description,
        )

    async def retrieve_chunks(
        self,
        user: User,
        *,
        query: str,
        document_ids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not settings.RAG_ENABLED:
            return []
        return await LegacyAiDocumentService(self.db).retrieve_chunks(
            user_id=user.id,
            query=query,
            document_ids=document_ids,
            top_k=top_k,
        )

    @staticmethod
    def _require_rag_documents() -> None:
        if not settings.RAG_ENABLED:
            raise HTTPException(status_code=503, detail="RAG is disabled")

    async def _resolve_prompt_version(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
    ) -> tuple[AiPromptTemplate | None, AiPromptVersion]:
        if prompt_version_id:
            version = await self.repo.get_prompt_version(prompt_version_id)
            if not version:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            template = await self.repo.get_prompt_template_for_user(
                user.id, version.prompt_template_id
            )
            if not template:
                raise HTTPException(status_code=404, detail="Prompt template not found")
            return template, version
        if not prompt_template_key:
            raise HTTPException(
                status_code=422,
                detail="prompt_template_key or prompt_version_id is required",
            )
        template = await self.repo.get_prompt_template_by_key_for_user(
            user.id, prompt_template_key
        )
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions, _ = await self.repo.list_prompt_versions(
            template.id, limit=MAX_PAGE_LIMIT, offset=0
        )
        version = None
        if template.active_version_id:
            version = next(
                (item for item in versions if item.id == template.active_version_id), None
            )
        if version is None:
            version = next((item for item in versions if item.is_published), None)
        if version is None and versions:
            version = versions[0]
        if version is None:
            raise HTTPException(status_code=422, detail="This prompt template has no versions yet")
        return template, version

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
    ):
        template, version = await self._resolve_prompt_version(
            user,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
        )
        matches: list[dict[str, Any]] = []
        if retrieval_query:
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

        rendered_system_prompt = _render_template(version.system_prompt, variables)
        if additional_system_context:
            rendered_system_prompt = (
                f"{rendered_system_prompt.rstrip()}\n\n{additional_system_context}"
            )
        rendered_user_prompt = _render_template(version.user_prompt_template, variables)
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
            retrieved_chunk_ids_json=[item["chunk_id"] for item in matches],
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

    async def run_rag_answer(
        self,
        user: User,
        *,
        query: str,
        combined_context: str,
        retrieved_chunk_ids: list[str],
        review_required: bool = False,
    ) -> AiRun:
        prompt_spec = await resolve_rag_answer_prompt(self.repo, user)

        reference_context = combined_context.strip()
        rendered_system_prompt = (
            f"{prompt_spec.system_prompt}\n\n{reference_context}"
            if reference_context
            else prompt_spec.system_prompt
        )
        rendered_user_prompt = query

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
        started = perf_counter()
        try:
            result = await provider.generate(
                ProviderGenerateRequest(
                    model=version.model_name,
                    system_prompt=rendered_system_prompt,
                    user_prompt=rendered_user_prompt,
                    response_format=version.response_format,
                    temperature=version.temperature,
                )
            )
            latency_ms = int((perf_counter() - started) * 1000)
            run.status = "completed"
            run.output_text = result.output_text
            run.output_json = result.output_json
            run.latency_ms = latency_ms
            run.input_tokens = result.input_tokens
            run.output_tokens = result.output_tokens
            run.total_tokens = result.total_tokens
            run.estimated_cost_micros = (
                (result.input_tokens * version.input_cost_per_million)
                + (result.output_tokens * version.output_cost_per_million)
            )
            run.completed_at = datetime.now(UTC)
        except HTTPException as exc:
            run.status = "failed"
            run.error_message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise
        except Exception as exc:
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

    async def list_runs(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_runs_for_user(user.id, limit=limit, offset=offset)

    async def create_review(self, user: User, run_id: str, assigned_to_user_id: str | None):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        review = await self.repo.create_review(
            run_id=run.id,
            requested_by_user_id=user.id,
            assigned_to_user_id=assigned_to_user_id,
            status="pending",
        )
        run.review_status = "pending"
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def list_reviews(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_reviews_for_user(user.id, limit=limit, offset=offset)

    async def decide_review(self, user: User, review_id: str, payload: dict[str, Any]):
        review = await self.repo.get_review(review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review item not found")
        if not user.is_admin and user.id not in {
            review.requested_by_user_id,
            review.assigned_to_user_id,
        }:
            raise HTTPException(status_code=403, detail="You are not allowed to decide this review")
        run = await self.repo.get_run_for_user(review.requested_by_user_id, review.run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        review.status = payload["status"]
        review.reviewed_by_user_id = user.id
        review.reviewer_notes = payload.get("reviewer_notes")
        review.corrected_output = payload.get("corrected_output")
        run.review_status = payload["status"]
        if payload.get("corrected_output"):
            run.output_text = payload["corrected_output"]
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def add_feedback(
        self, user: User, run_id: str, rating: int,
        comment: str | None, corrected_output: str | None,
    ):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        feedback = await self.repo.create_feedback(
            run_id=run.id,
            user_id=user.id,
            rating=rating,
            comment=comment,
            corrected_output=corrected_output,
        )
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def list_feedback(
        self,
        user: User,
        run_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        return await self.repo.list_feedback_for_run(run.id, limit=limit, offset=offset)

    async def list_datasets(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_datasets_for_user(user.id, limit=limit, offset=offset)

    async def create_dataset(self, user: User, name: str, description: str | None):
        dataset = await self.repo.create_dataset(
            user_id=user.id, name=name, description=description
        )
        await self.db.commit()
        await self.db.refresh(dataset)
        return dataset

    async def update_dataset(self, user: User, dataset_id: str, updates: dict[str, Any]):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        for field, value in updates.items():
            setattr(dataset, field, value)
        await self.db.commit()
        await self.db.refresh(dataset)
        return dataset

    async def list_dataset_cases(
        self,
        user: User,
        dataset_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        return await self.repo.list_dataset_cases(
            dataset.id, limit=limit, offset=offset
        )

    async def create_dataset_case(self, user: User, dataset_id: str, payload: dict[str, Any]):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        case = await self.repo.create_dataset_case(
            dataset_id=dataset.id,
            input_variables_json=payload["input_variables"],
            expected_output_text=payload["expected_output_text"],
            expected_output_json=payload["expected_output_json"],
            notes=payload["notes"],
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def _list_all_dataset_cases(self, dataset_id: str):
        cases, total = await self.repo.list_dataset_cases(
            dataset_id, limit=MAX_PAGE_LIMIT, offset=0
        )
        offset = len(cases)
        while offset < total:
            page, _ = await self.repo.list_dataset_cases(
                dataset_id, limit=MAX_PAGE_LIMIT, offset=offset
            )
            cases.extend(page)
            offset += len(page)
        return cases

    async def _execute_evaluation_case(
        self,
        *,
        user: User,
        template: AiPromptTemplate,
        version: AiPromptVersion,
        dataset_id: str,
        case,
    ) -> _EvaluationCaseResult:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            case_service = AiService(db)
            ai_run = await case_service.run_prompt(
                user,
                prompt_template_key=template.key,
                prompt_version_id=version.id,
                variables=case.input_variables_json,
                retrieval_query=None,
                document_ids=[],
                top_k=0,
                review_required=False,
                evaluation_dataset_id=dataset_id,
                evaluation_case_id=case.id,
            )
            score, passed, notes = self._score_evaluation_case(
                ai_run.output_text, ai_run.output_json, case
            )
            return _EvaluationCaseResult(
                case_id=case.id,
                ai_run_id=ai_run.id,
                score=score,
                passed=passed,
                notes=notes,
            )

    async def queue_evaluation(
        self, user: User, dataset_id: str, prompt_version_id: str
    ) -> AiEvaluationRun:
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        version = await self.repo.get_prompt_version(prompt_version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        template = await self.repo.get_prompt_template_for_user(user.id, version.prompt_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")

        cases = await self._list_all_dataset_cases(dataset.id)
        evaluation_run = await self.repo.create_evaluation_run(
            dataset_id=dataset.id,
            prompt_version_id=version.id,
            user_id=user.id,
            status="running",
            total_cases=len(cases),
            passed_cases=0,
            average_score=0,
        )
        await self.db.commit()
        await self.db.refresh(evaluation_run)

        from backend.workers.evaluation import queue_evaluation_run

        queue_evaluation_run(
            evaluation_run_id=evaluation_run.id,
            user_id=user.id,
            dataset_id=dataset.id,
            prompt_version_id=version.id,
        )
        return evaluation_run

    async def execute_evaluation_run(
        self,
        *,
        evaluation_run_id: str,
        user_id: str,
        dataset_id: str,
        prompt_version_id: str,
    ) -> None:
        try:
            user = await IdentityRepository(self.db).get_user_by_id(user_id)
            if not user:
                await self._mark_evaluation_run_failed(
                    evaluation_run_id, notes="User not found for evaluation run"
                )
                return

            dataset = await self.repo.get_dataset_for_user(user_id, dataset_id)
            if not dataset:
                await self._mark_evaluation_run_failed(
                    evaluation_run_id, notes="Evaluation dataset not found"
                )
                return
            version = await self.repo.get_prompt_version(prompt_version_id)
            if not version:
                await self._mark_evaluation_run_failed(
                    evaluation_run_id, notes="Prompt version not found"
                )
                return
            template = await self.repo.get_prompt_template_for_user(
                user_id, version.prompt_template_id
            )
            if not template:
                await self._mark_evaluation_run_failed(
                    evaluation_run_id, notes="Prompt template not found"
                )
                return

            evaluation_run = await self.repo.get_evaluation_run_by_id(evaluation_run_id)
            if not evaluation_run:
                logger.warning("Evaluation run %s not found; skipping worker execution", evaluation_run_id)
                return
            if evaluation_run.status != "running":
                logger.info(
                    "Evaluation run %s already in status=%s; skipping",
                    evaluation_run_id,
                    evaluation_run.status,
                )
                return

            cases = await self._list_all_dataset_cases(dataset.id)
            evaluation_run.total_cases = len(cases)
            concurrency = max(1, settings.AI_EVALUATION_CONCURRENCY)
            semaphore = asyncio.Semaphore(concurrency)

            async def _run_case(case):
                async with semaphore:
                    return await self._execute_evaluation_case(
                        user=user,
                        template=template,
                        version=version,
                        dataset_id=dataset.id,
                        case=case,
                    )

            results = await asyncio.gather(*[_run_case(case) for case in cases])
            passed_cases = 0
            scores: list[float] = []
            item_payloads: list[dict] = []
            for result in results:
                scores.append(result.score)
                if result.passed:
                    passed_cases += 1
                item_payloads.append(
                    {
                        "evaluation_run_id": evaluation_run.id,
                        "evaluation_case_id": result.case_id,
                        "ai_run_id": result.ai_run_id,
                        "score": result.score,
                        "passed": result.passed,
                        "notes": result.notes,
                    }
                )
            if item_payloads:
                await self.repo.create_evaluation_run_items_batch(item_payloads)
            evaluation_run.status = "completed"
            evaluation_run.passed_cases = passed_cases
            evaluation_run.average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
            evaluation_run.completed_at = datetime.now(UTC)
            await self.db.commit()
        except Exception:
            logger.exception("AI evaluation run %s failed", evaluation_run_id)
            await self._mark_evaluation_run_failed(evaluation_run_id)
            raise

    async def _mark_evaluation_run_failed(
        self, evaluation_run_id: str, *, notes: str | None = None
    ) -> None:
        if notes:
            logger.error("Evaluation run %s failed: %s", evaluation_run_id, notes)
        evaluation_run = await self.repo.get_evaluation_run_by_id(evaluation_run_id)
        if evaluation_run is None or evaluation_run.status != "running":
            return
        evaluation_run.status = "failed"
        evaluation_run.completed_at = datetime.now(UTC)
        await self.db.commit()

    def _score_evaluation_case(
        self, output_text: str | None, output_json: dict | None, case
    ) -> tuple[float, bool, str]:
        if case.expected_output_json is not None:
            passed = output_json == case.expected_output_json
            return (1.0 if passed else 0.0, passed, "JSON exact match")
        expected_text = (case.expected_output_text or "").strip()
        actual_text = (output_text or "").strip()
        if expected_text:
            passed = expected_text.lower() == actual_text.lower()
            if passed:
                return 1.0, True, "Exact text match"
            partial = 1.0 if expected_text.lower() in actual_text.lower() else 0.0
            return partial, partial >= 1.0, "Substring text comparison"
        return 0.0, False, "No expected output defined"

    async def list_evaluation_runs(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_evaluation_runs_for_user(
            user.id, limit=limit, offset=offset
        )

    async def get_overview(self, user: User):
        (
            prompt_templates_result,
            recent_runs_result,
            documents_result,
            datasets_result,
        ) = await asyncio.gather(
            self.repo.list_prompt_templates_for_user(
                user.id, limit=DEFAULT_PAGE_LIMIT, offset=0
            ),
            self.repo.list_runs_for_user(user.id, limit=10, offset=0),
            self.list_documents(user, limit=DEFAULT_PAGE_LIMIT, offset=0),
            self.repo.list_datasets_for_user(
                user.id, limit=DEFAULT_PAGE_LIMIT, offset=0
            ),
        )
        prompt_templates, _ = prompt_templates_result
        recent_runs, _ = recent_runs_result
        documents, _ = documents_result
        datasets, _ = datasets_result
        return {
            "providers": self.list_provider_descriptors(),
            "prompt_templates": prompt_templates,
            "recent_runs": recent_runs,
            "documents": documents,
            "datasets": datasets,
        }
