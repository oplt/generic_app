"""Persistence helpers for the RAG evaluation workbench."""

from __future__ import annotations

from backend.modules.rag.infrastructure.models import (
    RagEvaluationCase,
    RagEvaluationDataset,
    RagEvaluationRun,
    RagEvaluationRunItem,
)
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class RagEvaluationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _dataset_tenant_clause(*, user_id: str, organization_id: str | None):
        if organization_id:
            return RagEvaluationDataset.organization_id == organization_id
        return RagEvaluationDataset.user_id == user_id

    @staticmethod
    def _run_tenant_clause(*, user_id: str, organization_id: str | None):
        if organization_id:
            return RagEvaluationRun.organization_id == organization_id
        return RagEvaluationRun.user_id == user_id

    async def list_datasets(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RagEvaluationDataset], int]:
        tenant = self._dataset_tenant_clause(user_id=user_id, organization_id=organization_id)
        stmt: Select = (
            select(RagEvaluationDataset)
            .where(tenant)
            .order_by(RagEvaluationDataset.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.db.scalars(stmt)).all())
        total = await self.db.scalar(select(func.count(RagEvaluationDataset.id)).where(tenant))
        return rows, int(total or 0)

    async def get_dataset(
        self,
        dataset_id: str,
        *,
        user_id: str,
        organization_id: str | None,
    ) -> RagEvaluationDataset | None:
        return await self.db.scalar(
            select(RagEvaluationDataset).where(
                RagEvaluationDataset.id == dataset_id,
                self._dataset_tenant_clause(user_id=user_id, organization_id=organization_id),
            )
        )

    async def create_dataset(self, **kwargs) -> RagEvaluationDataset:
        row = RagEvaluationDataset(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_cases(self, dataset_id: str) -> list[RagEvaluationCase]:
        result = await self.db.scalars(
            select(RagEvaluationCase)
            .where(RagEvaluationCase.dataset_id == dataset_id)
            .order_by(RagEvaluationCase.created_at.asc(), RagEvaluationCase.id.asc())
        )
        return list(result.all())

    async def create_case(self, **kwargs) -> RagEvaluationCase:
        row = RagEvaluationCase(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def create_run(self, **kwargs) -> RagEvaluationRun:
        row = RagEvaluationRun(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_run(
        self,
        run_id: str,
        *,
        user_id: str,
        organization_id: str | None,
    ) -> RagEvaluationRun | None:
        return await self.db.scalar(
            select(RagEvaluationRun).where(
                RagEvaluationRun.id == run_id,
                self._run_tenant_clause(user_id=user_id, organization_id=organization_id),
            )
        )

    async def list_runs(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        dataset_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RagEvaluationRun], int]:
        clauses = [self._run_tenant_clause(user_id=user_id, organization_id=organization_id)]
        if dataset_id:
            clauses.append(RagEvaluationRun.dataset_id == dataset_id)
        stmt = (
            select(RagEvaluationRun)
            .where(*clauses)
            .order_by(RagEvaluationRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.db.scalars(stmt)).all())
        total = await self.db.scalar(select(func.count(RagEvaluationRun.id)).where(*clauses))
        return rows, int(total or 0)

    async def list_run_items(self, run_id: str) -> list[RagEvaluationRunItem]:
        result = await self.db.scalars(
            select(RagEvaluationRunItem)
            .where(RagEvaluationRunItem.run_id == run_id)
            .order_by(RagEvaluationRunItem.id.asc())
        )
        return list(result.all())

    async def create_run_item(self, **kwargs) -> RagEvaluationRunItem:
        row = RagEvaluationRunItem(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row
