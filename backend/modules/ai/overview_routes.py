from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.cache import cache_get_or_load_model, cache_key
from backend.core.config import settings
from backend.modules.ai.provider_service import AiProviderService
from backend.modules.ai.schemas import AiModuleOverviewResponse, AiProviderDescriptor
from backend.modules.ai.serializers import (
    _dataset_to_response,
    _document_to_response,
    _prompt_template_to_response,
    run_to_response,
)
from backend.modules.ai.service import AiService
from backend.modules.identity_access.models import User

router = APIRouter()


@router.get("/overview", response_model=AiModuleOverviewResponse)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async def load_overview() -> AiModuleOverviewResponse:
        overview = await AiService(db).get_overview(current_user)
        return AiModuleOverviewResponse(
            providers=overview["providers"],
            prompt_templates=[
                _prompt_template_to_response(item) for item in overview["prompt_templates"]
            ],
            recent_runs=[run_to_response(item) for item in overview["recent_runs"]],
            documents=[_document_to_response(item) for item in overview["documents"]],
            datasets=[_dataset_to_response(item) for item in overview["datasets"]],
            prompt_templates_count=overview["prompt_templates_count"],
            recent_runs_count=overview["recent_runs_count"],
            documents_count=overview["documents_count"],
            datasets_count=overview["datasets_count"],
        )

    return await cache_get_or_load_model(
        cache_key("ai", "overview", current_user.id),
        AiModuleOverviewResponse,
        ttl_seconds=settings.CACHE_AI_OVERVIEW_TTL_SECONDS,
        loader=load_overview,
    )


@router.get("/providers", response_model=list[AiProviderDescriptor])
async def list_providers():
    return AiProviderService.list_provider_descriptors()
