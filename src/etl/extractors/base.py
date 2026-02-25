from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from shared.cursors import CursorStore

log = structlog.get_logger()


@dataclass
class ExtractResult:
    source: str
    records_written: int
    kinds: dict[str, int]
    duration_ms: int


class BaseExtractor(ABC):
    source: str

    @abstractmethod
    async def preflight(self) -> bool: ...

    @abstractmethod
    async def extract(self, pool: asyncpg.Pool, cursors: CursorStore) -> ExtractResult: ...

    async def _write_records(
        self,
        pool: asyncpg.Pool,
        records: list[dict[str, Any]],
    ) -> int:
        if not records:
            return 0

        written = 0
        async with pool.acquire() as conn:
            stmt = await conn.prepare(
                """
                INSERT INTO raw_records (source, kind, external_id, fetched_at, content_hash, data)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (source, kind, external_id, content_hash) DO NOTHING
                """
            )
            now = datetime.now(UTC).isoformat()
            for rec in records:
                chash = _content_hash(rec["data"])
                result = await stmt.execute(
                    rec["source"],
                    rec["kind"],
                    rec["external_id"],
                    now,
                    chash,
                    json.dumps(rec["data"], default=str),
                )
                if result and result.endswith("1"):
                    written += 1

        return written


def _content_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_record(source: str, kind: str, external_id: str, data: Any) -> dict[str, Any]:
    return {
        "source": source,
        "kind": kind,
        "external_id": str(external_id),
        "data": data,
    }
