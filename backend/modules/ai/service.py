from backend.modules.ai.application.overview_coordinator import AiOverviewCoordinator
from backend.modules.ai.evaluation_service import AiEvaluationService, _EvaluationCaseResult
from backend.modules.ai.provider_service import AiProviderService
from backend.modules.ai.review_service import AiReviewService
from backend.modules.identity_access.models import User


class AiService(AiEvaluationService):
    """Thin coordinator; legacy capability methods delegate explicitly."""

    def __init__(self, db):
        super().__init__(db)
        self.review_service = AiReviewService(db)

    async def create_review(self, *args, **kwargs):
        return await self.review_service.create_review(*args, **kwargs)

    async def list_reviews(self, *args, **kwargs):
        return await self.review_service.list_reviews(*args, **kwargs)

    async def decide_review(self, *args, **kwargs):
        return await self.review_service.decide_review(*args, **kwargs)

    async def add_feedback(self, *args, **kwargs):
        return await self.review_service.add_feedback(*args, **kwargs)

    async def list_feedback(self, *args, **kwargs):
        return await self.review_service.list_feedback(*args, **kwargs)

    @staticmethod
    def list_provider_descriptors():
        return AiProviderService.list_provider_descriptors()

    async def get_overview(self, user: User):
        return await AiOverviewCoordinator(
            self.repo,
            list_documents=self.list_documents,
            count_documents=self.count_documents,
        ).build(user, self.list_provider_descriptors)


__all__ = ["AiService", "_EvaluationCaseResult"]
