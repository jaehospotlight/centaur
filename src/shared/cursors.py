from __future__ import annotations

from datetime import datetime, timedelta

import asyncpg
import structlog

log = structlog.get_logger()

CURSOR_OVERLAP_SECONDS = 300


class CursorStore:
    async def get(
        self, pool: asyncpg.Pool, source: str, kind: str, entity_id: str | None = None
    ) -> str | None:
        key = _cursor_key(source, kind, entity_id)
        row = await pool.fetchrow("SELECT cursor FROM sync_cursors WHERE cursor_key = $1", key)
        return row["cursor"] if row else None

    async def set(
        self,
        pool: asyncpg.Pool,
        source: str,
        kind: str,
        cursor: str,
        entity_id: str | None = None,
    ) -> None:
        key = _cursor_key(source, kind, entity_id)
        await pool.execute(
            """
            INSERT INTO sync_cursors (cursor_key, source, kind, entity_id, cursor, updated_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (cursor_key) DO UPDATE SET
                cursor = EXCLUDED.cursor,
                updated_at = EXCLUDED.updated_at
            """,
            key,
            source,
            kind,
            entity_id,
            cursor,
        )

    @staticmethod
    def apply_overlap(cursor: str, overlap_seconds: int = CURSOR_OVERLAP_SECONDS) -> str:
        try:
            dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            adjusted = dt - timedelta(seconds=overlap_seconds)
            return adjusted.isoformat()
        except ValueError:
            try:
                ts = float(cursor)
                return str(ts - overlap_seconds)
            except ValueError:
                return cursor


def _cursor_key(source: str, kind: str, entity_id: str | None = None) -> str:
    if entity_id:
        return f"{source}:{kind}:{entity_id}"
    return f"{source}:{kind}"


def track_max_timestamp(items: list[dict], field: str) -> str | None:
    max_val: str | None = None
    for item in items:
        val = item.get(field)
        if val is None:
            continue
        s = val if isinstance(val, str) else str(val)
        if max_val is None or s > max_val:
            max_val = s
    return max_val
