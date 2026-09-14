from __future__ import annotations

from fastapi import HTTPException

from backend.lib.project_access import ProjectAccessPort
from backend.modules.memory.domain.enums import MemoryLevel
from backend.modules.memory.domain.models import MemoryItem


class MemoryAuthorization:
    """Owns memory read/write scope checks, separate from provider orchestration."""

    def __init__(self, project_access: ProjectAccessPort):
        self.project_access = project_access

    async def authorize_write(
        self, *, user_id: str, memory_level: MemoryLevel, project_id: str | None
    ) -> None:
        if memory_level == MemoryLevel.PROJECT:
            if not project_id:
                raise HTTPException(
                    status_code=422,
                    detail="project_id is required for project memory",
                )
            await self.ensure_project_access(user_id, project_id)

    async def authorize_read_item(self, user_id: str, item: MemoryItem) -> bool:
        return bool(await self.filter_authorized_read_items(user_id, [item]))

    async def filter_authorized_read_items(
        self, user_id: str, items: list[MemoryItem]
    ) -> list[MemoryItem]:
        if not items:
            return []
        project_ids = {
            item.metadata.project_id
            for item in items
            if item.metadata.memory_level == MemoryLevel.PROJECT
            and item.metadata.project_id
            and item.metadata.user_id == user_id
        }
        accessible_project_ids = await self.project_access.filter_accessible_project_ids(
            user_id, project_ids
        )
        return [
            item
            for item in items
            if self._item_authorized_for_read(user_id, item, accessible_project_ids)
        ]

    @staticmethod
    def _item_authorized_for_read(
        user_id: str, item: MemoryItem, accessible_project_ids: set[str]
    ) -> bool:
        level = item.metadata.memory_level
        if level in {MemoryLevel.USER, MemoryLevel.SESSION, MemoryLevel.EPISODIC}:
            return item.metadata.user_id == user_id
        if level == MemoryLevel.PROJECT:
            if item.metadata.user_id != user_id:
                return False
            return (
                not item.metadata.project_id
                or item.metadata.project_id in accessible_project_ids
            )
        if level == MemoryLevel.AGENT:
            scope = item.metadata.scope
            if scope and scope.value == "global_agent":
                return True
            return item.metadata.user_id in {"", user_id}
        return False

    async def ensure_project_access(self, user_id: str, project_id: str) -> None:
        project = await self.project_access.get_project_for_user(project_id, user_id)
        if not project:
            raise HTTPException(status_code=403, detail="Project access denied")
