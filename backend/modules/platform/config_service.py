from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import (
    PLATFORM_CONFIG_CACHE_KEY,
    cache_get_or_load_model,
    invalidate_platform_caches,
)
from backend.core.config import settings
from backend.modules.manifests import (
    ModuleManifestError,
    effective_modules,
    frontend_routes_for_modules,
    get_manifest_map,
    nav_entries_for_modules,
)
from backend.modules.platform.defaults import (
    DEFAULT_EMAIL_TEMPLATES,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_PLANS,
    MODULE_CATALOG,
    MODULE_PACKS,
    SETTING_APP_NAME,
    SETTING_CORE_DOMAIN_PLURAL,
    SETTING_CORE_DOMAIN_SINGULAR,
    SETTING_MFA_ENABLED,
    SETTING_MODULE_OVERRIDE_PREFIX,
    SETTING_MODULE_PACK,
)
from backend.modules.platform.profiles import (
    CAPABILITY_PROFILES,
    CapabilityProfileError,
    profile_resolution_payload,
    resolve_capability_profile,
)
from backend.modules.platform.repository import PlatformRepository
from backend.modules.platform.schemas import (
    CapabilityProfileSummary,
    ModuleCatalogItem,
    ModuleFrontendRoute,
    ModuleNavEntry,
    ModulePackResponse,
    PlatformConfigResponse,
    PlatformMetadataResponse,
)
from backend.modules.settings.repository import SettingsRepository


class PlatformConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PlatformRepository(db)
        self.settings_repo = SettingsRepository(db)

    async def ensure_defaults(self) -> None:
        setting_defaults = (
            (SETTING_APP_NAME, settings.APP_NAME, "Clone-specific app display name."),
            (
                SETTING_CORE_DOMAIN_SINGULAR,
                settings.CORE_DOMAIN_SINGULAR,
                "Singular label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_CORE_DOMAIN_PLURAL,
                settings.CORE_DOMAIN_PLURAL,
                "Plural label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_MODULE_PACK,
                settings.PLATFORM_DEFAULT_MODULE_PACK,
                "Active capability profile (module pack) for optional platform capabilities.",
            ),
            (
                SETTING_MFA_ENABLED,
                "false",
                "Whether MFA authentication is shown and enforced on login.",
            ),
        )
        default_settings = [
            {"key": key, "value": value, "description": description}
            for key, value, description in setting_defaults
        ]
        inserted = sum(
            (
                await self.settings_repo.upsert_defaults(default_settings),
                await self.repo.upsert_default_plans(list(DEFAULT_PLANS)),
                await self.repo.upsert_default_feature_flags(list(DEFAULT_FEATURE_FLAGS)),
                await self.repo.upsert_default_email_templates(list(DEFAULT_EMAIL_TEMPLATES)),
            )
        )
        await self.db.commit()
        if inserted:
            await invalidate_platform_caches()

    async def get_platform_metadata(self) -> PlatformMetadataResponse:
        config = await self.get_platform_config()
        return PlatformMetadataResponse(
            app_name=config.app_name,
            core_domain_singular=config.core_domain_singular,
            core_domain_plural=config.core_domain_plural,
            module_pack=config.module_pack,
            capability_profile=config.capability_profile,
            enabled_modules=config.enabled_modules,
            active_modules=config.active_modules,
            module_catalog=config.module_catalog,
            available_module_packs=config.available_module_packs,
            available_capability_profiles=config.available_capability_profiles,
            active_profile=config.active_profile,
            module_nav=config.module_nav,
            module_routes=config.module_routes,
            mfa_enabled=config.mfa_enabled,
        )

    async def get_platform_config(self) -> PlatformConfigResponse:
        return await cache_get_or_load_model(
            PLATFORM_CONFIG_CACHE_KEY,
            PlatformConfigResponse,
            ttl_seconds=settings.CACHE_PLATFORM_TTL_SECONDS,
            loader=self._load_platform_config,
        )

    async def _load_platform_config(self) -> PlatformConfigResponse:
        platform_settings = await self.settings_repo.list_by_prefix("platform.")
        setting_map = {item.key: item.value for item in platform_settings}

        module_pack = setting_map.get(SETTING_MODULE_PACK, settings.PLATFORM_DEFAULT_MODULE_PACK)
        if module_pack not in MODULE_PACKS:
            module_pack = settings.PLATFORM_DEFAULT_MODULE_PACK

        explicit_overrides: dict[str, bool] = {}
        for item in MODULE_CATALOG:
            raw_value = setting_map.get(f"{SETTING_MODULE_OVERRIDE_PREFIX}{item['key']}")
            if raw_value is not None:
                explicit_overrides[item["key"]] = self._parse_bool(raw_value)

        enabled_modules = self._resolve_enabled_modules(module_pack, explicit_overrides)
        try:
            active = effective_modules(enabled_modules)
            active_profile_resolution = resolve_capability_profile(
                module_pack,
                module_overrides=explicit_overrides,
            )
        except (ModuleManifestError, CapabilityProfileError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        module_catalog = [
            ModuleCatalogItem(
                key=item["key"],
                label=item["label"],
                description=item["description"],
                user_visible=item["user_visible"],
                enabled=item["key"] in enabled_modules,
            )
            for item in MODULE_CATALOG
        ]

        mfa_enabled = self._parse_bool(setting_map.get(SETTING_MFA_ENABLED, "false"))
        active_sorted = sorted(active)
        nav_payload = nav_entries_for_modules(active)
        route_payload = frontend_routes_for_modules(active)
        available_profiles = [
            CapabilityProfileSummary.model_validate(
                profile_resolution_payload(resolve_capability_profile(key))
            )
            for key in CAPABILITY_PROFILES
        ]

        return PlatformConfigResponse(
            app_name=setting_map.get(SETTING_APP_NAME, settings.APP_NAME),
            core_domain_singular=setting_map.get(
                SETTING_CORE_DOMAIN_SINGULAR, settings.CORE_DOMAIN_SINGULAR
            ),
            core_domain_plural=setting_map.get(
                SETTING_CORE_DOMAIN_PLURAL, settings.CORE_DOMAIN_PLURAL
            ),
            module_pack=module_pack,
            capability_profile=module_pack,
            enabled_modules=enabled_modules,
            active_modules=active_sorted,
            module_catalog=module_catalog,
            available_module_packs=[
                ModulePackResponse(key=key, **pack_payload)
                for key, pack_payload in MODULE_PACKS.items()
            ],
            available_capability_profiles=available_profiles,
            active_profile=CapabilityProfileSummary.model_validate(
                profile_resolution_payload(active_profile_resolution)
            ),
            module_nav=[ModuleNavEntry.model_validate(item) for item in nav_payload],
            module_routes=[ModuleFrontendRoute.model_validate(item) for item in route_payload],
            module_overrides=explicit_overrides,
            mfa_enabled=mfa_enabled,
        )

    async def update_platform_config(
        self,
        *,
        app_name: str | None,
        core_domain_singular: str | None,
        core_domain_plural: str | None,
        module_pack: str | None,
        module_overrides: dict[str, bool] | None,
        mfa_enabled: bool | None,
        commit: bool = True,
    ) -> PlatformConfigResponse:
        current_config = await self.get_platform_config()
        next_pack = module_pack or current_config.module_pack
        if next_pack not in MODULE_PACKS:
            raise HTTPException(status_code=422, detail="Unknown capability profile")

        if app_name is not None:
            await self._upsert_setting(
                SETTING_APP_NAME, app_name, "Clone-specific app display name."
            )
        if core_domain_singular is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_SINGULAR,
                core_domain_singular,
                "Singular label for the core domain surfaced in the UI.",
            )
        if core_domain_plural is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_PLURAL,
                core_domain_plural,
                "Plural label for the core domain surfaced in the UI.",
            )
        if module_pack is not None:
            await self._upsert_setting(
                SETTING_MODULE_PACK,
                module_pack,
                "Active capability profile (module pack) for optional platform capabilities.",
            )

        if mfa_enabled is not None:
            await self._upsert_setting(
                SETTING_MFA_ENABLED,
                self._serialize_bool(mfa_enabled),
                "Whether MFA authentication is shown and enforced on login.",
            )

        if module_overrides is not None:
            pack_modules = set(MODULE_PACKS[next_pack]["modules"])
            valid_module_keys = {item["key"] for item in MODULE_CATALOG}
            for key, enabled in module_overrides.items():
                if key not in valid_module_keys:
                    raise HTTPException(status_code=422, detail=f"Unknown module key: {key}")
                setting_key = f"{SETTING_MODULE_OVERRIDE_PREFIX}{key}"
                should_exist = enabled != (key in pack_modules)
                existing = await self.settings_repo.get_by_key(setting_key)
                if should_exist:
                    if existing is None:
                        await self.settings_repo.create(
                            key=setting_key,
                            value=self._serialize_bool(enabled),
                            description=f"Explicit module override for {key}.",
                        )
                    else:
                        existing.value = self._serialize_bool(enabled)
                elif existing is not None:
                    await self.settings_repo.delete(existing)

        if commit:
            await self.db.commit()
        await invalidate_platform_caches()
        return await self._load_platform_config()

    async def ensure_module_enabled(self, module_key: str) -> None:
        metadata = await self.get_platform_metadata()
        active = set(metadata.active_modules) | set(metadata.enabled_modules)
        if module_key not in active:
            raise HTTPException(status_code=404, detail=f"Module `{module_key}` is not enabled")

    async def _upsert_setting(self, key: str, value: str, description: str) -> None:
        setting = await self.settings_repo.get_by_key(key)
        if setting is None:
            await self.settings_repo.create(key=key, value=value, description=description)
        else:
            setting.value = value
            setting.description = description

    @staticmethod
    def _resolve_enabled_modules(
        module_pack: str, explicit_overrides: dict[str, bool]
    ) -> list[str]:
        enabled = set(MODULE_PACKS[module_pack]["modules"])
        for key, value in explicit_overrides.items():
            if value:
                enabled.add(key)
            else:
                enabled.discard(key)
        # Pack lists may include always-on keys for docs; only optional catalog keys
        # are returned as enabled_modules for API compatibility.
        optional_keys = {item["key"] for item in MODULE_CATALOG}
        known = set(get_manifest_map())
        enabled &= known
        ordered_module_keys = [item["key"] for item in MODULE_CATALOG]
        return [key for key in ordered_module_keys if key in enabled and key in optional_keys]

    @staticmethod
    def _parse_bool(raw_value: str) -> bool:
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _serialize_bool(value: bool) -> str:
        return "true" if value else "false"
