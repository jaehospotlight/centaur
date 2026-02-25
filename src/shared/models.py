from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawRecord(BaseModel):
    source: str
    kind: str
    external_id: str
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    content_hash: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SyncCursor(BaseModel):
    cursor_key: str
    source: str
    kind: str
    entity_id: str | None = None
    cursor: str
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Person(BaseModel):
    slug: str
    name: str
    email: str | None = None
    role: str | None = None
    is_direct_report: bool = False
    focus_area: str | None = None


class EntityMapping(BaseModel):
    source: str
    external_id: str
    person_slug: str


class EmbeddingRecord(BaseModel):
    id: int | None = None
    source: str
    kind: str
    source_id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
