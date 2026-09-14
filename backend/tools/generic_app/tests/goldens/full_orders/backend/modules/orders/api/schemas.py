from datetime import datetime

from pydantic import BaseModel, Field

from backend.core.schemas import RequestModel


class OrderCreate(RequestModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class OrderUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class OrderResponse(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
