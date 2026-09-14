from backend.modules.platform.api_key_service import ApiKeyService
from backend.modules.platform.billing_service import BillingService
from backend.modules.platform.config_service import PlatformConfigService
from backend.modules.platform.email_template_service import EmailTemplateService
from backend.modules.platform.feature_flag_service import FeatureFlagService
from backend.modules.platform.webhook_service import WebhookService


class PlatformService(PlatformConfigService):
    """Thin coordinator over explicit platform capability services."""

    def __init__(self, db):
        super().__init__(db)
        self.billing = BillingService(db)
        self.api_keys = ApiKeyService(db)
        self.webhooks = WebhookService(db)
        self.feature_flags = FeatureFlagService(db)
        self.email_templates = EmailTemplateService(db)

    async def list_feature_flags(self, *args, **kwargs):
        loader = self.__dict__.get("_load_feature_flags_for_cache")
        if loader is not None:
            self.feature_flags._load_feature_flags_for_cache = loader
        return await self.feature_flags.list_feature_flags(*args, **kwargs)

    def _load_feature_flags_for_cache(self, *args, **kwargs):
        return self.feature_flags._load_feature_flags_for_cache(*args, **kwargs)

    def __getattr__(self, name):
        for capability in (
            self.billing,
            self.api_keys,
            self.webhooks,
            self.feature_flags,
            self.email_templates,
        ):
            try:
                return getattr(capability, name)
            except AttributeError:
                continue
        raise AttributeError(name)
