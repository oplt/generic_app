from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from backend.core.pagination import DEFAULT_PAGE_LIMIT
from backend.modules.ai.base_service import AiBaseService
from backend.modules.ai.models import AiPromptTemplate, AiPromptVersion
from backend.modules.ai.prompt_cache import invalidate_prompt_resolution_cache, resolve_prompt
from backend.modules.identity_access.models import User

PLACEHOLDER_PATTERN = re.compile(r"{{\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*}}")


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


class AiPromptService(AiBaseService):
    async def list_prompt_templates(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ):
        return await self.repo.list_prompt_templates_for_user(user.id, limit=limit, offset=offset)

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
        await invalidate_prompt_resolution_cache(user.id, template_key=template.key)
        return template

    async def update_prompt_template(self, user: User, template_id: str, updates: dict[str, Any]):
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
        template_key = template.key
        for field, value in updates.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        await invalidate_prompt_resolution_cache(user.id, template_key=template_key)
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
        await invalidate_prompt_resolution_cache(
            user.id,
            template_key=template.key,
            version_id=version.id,
        )
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
        await invalidate_prompt_resolution_cache(
            user.id,
            template_key=template.key,
            version_id=version.id,
        )
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
        return await self.repo.list_prompt_versions(template.id, limit=limit, offset=offset)

    async def _resolve_prompt_version(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
    ) -> tuple[AiPromptTemplate | None, AiPromptVersion]:
        if prompt_version_id:
            resolved = await resolve_prompt(
                self.repo,
                user,
                version_id=prompt_version_id,
            )
            if not resolved:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            return resolved
        if not prompt_template_key:
            raise HTTPException(
                status_code=422,
                detail="prompt_template_key or prompt_version_id is required",
            )
        resolved = await resolve_prompt(self.repo, user, template_key=prompt_template_key)
        if not resolved:
            template = await self.repo.get_prompt_template_by_key_for_user(
                user.id, prompt_template_key
            )
            if not template:
                raise HTTPException(status_code=404, detail="Prompt template not found")
            raise HTTPException(status_code=422, detail="This prompt template has no versions yet")
        return resolved
