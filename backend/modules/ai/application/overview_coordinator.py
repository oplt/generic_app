from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from backend.core.pagination import DEFAULT_PAGE_LIMIT
from backend.modules.identity_access.models import User


class AiOverviewCoordinator:
    """Coordinates the read-only AI overview without owning feature services."""

    def __init__(
        self,
        repo,
        *,
        list_documents: Callable[..., Awaitable[tuple[list, int]]],
        count_documents: Callable[..., Awaitable[int]],
    ):
        self.repo = repo
        self.list_documents = list_documents
        self.count_documents = count_documents

    async def build(self, user: User, list_provider_descriptors: Callable[[], list]):
        prompt_templates_result, recent_runs_result, documents_result, datasets_result, counts = (
            await asyncio.gather(
                self.repo.list_prompt_templates_for_user(
                    user.id, limit=DEFAULT_PAGE_LIMIT, offset=0
                ),
                self.repo.list_runs_for_user(user.id, limit=10, offset=0),
                self.list_documents(user, limit=DEFAULT_PAGE_LIMIT, offset=0),
                self.repo.list_datasets_for_user(user.id, limit=DEFAULT_PAGE_LIMIT, offset=0),
                asyncio.gather(
                    self.repo.count_prompt_templates_for_user(user.id),
                    self.repo.count_runs_for_user(user.id),
                    self.count_documents(user),
                    self.repo.count_datasets_for_user(user.id),
                ),
            )
        )
        prompt_templates, _ = prompt_templates_result
        recent_runs, _ = recent_runs_result
        documents, _ = documents_result
        datasets, _ = datasets_result
        return {
            "providers": list_provider_descriptors(),
            "prompt_templates": prompt_templates,
            "recent_runs": recent_runs,
            "documents": documents,
            "datasets": datasets,
            "prompt_templates_count": counts[0],
            "recent_runs_count": counts[1],
            "documents_count": counts[2],
            "datasets_count": counts[3],
        }
