from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from ..deps import get_pool

router = APIRouter()


@router.get("/health")
async def health(pool: Annotated[asyncpg.Pool, Depends(get_pool)]) -> dict:
    db_ok = False
    last_syncs: list[dict] = []
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            db_ok = True
            rows = await conn.fetch(
                """
                SELECT source, status, started_at, finished_at, records_synced
                FROM sync_runs
                WHERE (source, started_at) IN (
                    SELECT source, MAX(started_at) FROM sync_runs GROUP BY source
                )
                ORDER BY source
                """
            )
            last_syncs = [
                {
                    "source": r["source"],
                    "status": r["status"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                    "records_synced": r["records_synced"],
                }
                for r in rows
            ]
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "last_syncs": last_syncs,
    }
