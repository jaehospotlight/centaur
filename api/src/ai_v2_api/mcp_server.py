from __future__ import annotations

import json
from typing import Any

import asyncpg
from mcp.server.fastmcp import FastMCP

from .config import settings
from .deps import EmbeddingService

mcp = FastMCP("Tempo AI v2")

_pool: asyncpg.Pool | None = None


def set_pool(pool: asyncpg.Pool) -> None:
    global _pool
    _pool = pool


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


def _serialize(rows: list[asyncpg.Record]) -> str:
    return json.dumps([dict(r) for r in rows], default=str)


@mcp.tool()
async def search(
    query: str, sources: list[str] | None = None, limit: int = 20
) -> str:
    """Hybrid semantic + keyword search across all ingested data."""
    pool = _get_pool()
    svc = EmbeddingService(pool=pool)
    embedding = await svc.embed(query)
    embedding_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    source_filter = ""
    args: list[Any] = [query, limit]
    if sources:
        placeholders = ",".join(f"${i + 3}" for i in range(len(sources)))
        source_filter = f"AND source IN ({placeholders})"
        args.extend(sources)

    sql = f"""
    WITH vector_results AS (
        SELECT id, source, content, metadata, url,
               ROW_NUMBER() OVER (ORDER BY embedding <=> '{embedding_literal}'::vector) AS vector_rank
        FROM documents
        WHERE embedding IS NOT NULL {source_filter}
        ORDER BY embedding <=> '{embedding_literal}'::vector
        LIMIT $2
    ),
    fts_results AS (
        SELECT id, source, content, metadata, url,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank_cd(search_vector, plainto_tsquery('english', $1)) DESC
               ) AS fts_rank
        FROM documents
        WHERE search_vector @@ plainto_tsquery('english', $1) {source_filter}
        LIMIT $2
    ),
    combined AS (
        SELECT
            COALESCE(v.id, f.id) AS id,
            COALESCE(v.source, f.source) AS source,
            COALESCE(v.content, f.content) AS content,
            COALESCE(v.metadata, f.metadata) AS metadata,
            COALESCE(v.url, f.url) AS url,
            COALESCE(1.0 / (60 + v.vector_rank), 0) +
            COALESCE(1.0 / (60 + f.fts_rank), 0) AS rrf_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.id = f.id
    )
    SELECT source, content, metadata, url, rrf_score AS score
    FROM combined
    ORDER BY rrf_score DESC
    LIMIT $2
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return _serialize(rows)


@mcp.tool()
async def sql_query(query: str) -> str:
    """Run a read-only SQL query against the data plane."""
    import re

    disallowed = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
        re.IGNORECASE,
    )
    if disallowed.search(query):
        return json.dumps({"error": "Only read-only queries are allowed"})

    pool = _get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query)
        except Exception as e:
            return json.dumps({"error": str(e)})
    return _serialize(rows)


@mcp.tool()
async def get_slack_thread(channel: str, thread_ts: str) -> str:
    """Fetch a full Slack thread by channel and thread timestamp."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, channel, user_name, content, ts, metadata
            FROM slack_messages
            WHERE channel = $1 AND thread_ts = $2
            ORDER BY ts
            """,
            channel,
            thread_ts,
        )
    return _serialize(rows)


@mcp.tool()
async def get_person(slug: str) -> str:
    """Get a person's profile and recent activity by slug."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        person = await conn.fetchrow(
            """
            SELECT slug, display_name, emails, slack_id, github_username,
                   linear_id, metadata
            FROM people
            WHERE slug = $1
            """,
            slug,
        )
        if not person:
            return json.dumps({"error": "Person not found"})

        activity = await conn.fetch(
            """
            SELECT source, event_type, summary, occurred_at, url
            FROM activity_timeline
            WHERE actor = $1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
            slug,
        )

    result = {**dict(person), "recent_activity": [dict(r) for r in activity]}
    return json.dumps(result, default=str)


@mcp.tool()
async def get_timeline(
    days: int = 7, source: str | None = None, actor: str | None = None
) -> str:
    """Get the activity timeline for the last N days, optionally filtered."""
    pool = _get_pool()
    conditions = [f"occurred_at >= NOW() - INTERVAL '{days} days'"]
    args: list[Any] = []
    idx = 1

    if source:
        conditions.append(f"source = ${idx}")
        args.append(source)
        idx += 1
    if actor:
        conditions.append(f"actor = ${idx}")
        args.append(actor)
        idx += 1

    where = "WHERE " + " AND ".join(conditions)
    args.append(100)

    sql = f"""
    SELECT id, source, event_type, actor, summary, occurred_at, url, metadata
    FROM activity_timeline
    {where}
    ORDER BY occurred_at DESC
    LIMIT ${idx}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return _serialize(rows)


@mcp.tool()
async def list_sources() -> str:
    """List available data sources with record counts."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, COUNT(*) AS record_count
            FROM documents
            GROUP BY source
            ORDER BY source
            """
        )
    return _serialize(rows)


@mcp.tool()
async def sync_status() -> str:
    """Get current sync status for all data sources."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.source,
                c.cursor_value,
                c.updated_at AS cursor_updated_at,
                r.status AS last_run_status,
                r.started_at AS last_run_started,
                r.finished_at AS last_run_finished,
                r.records_synced AS last_run_records
            FROM sync_cursors c
            LEFT JOIN LATERAL (
                SELECT status, started_at, finished_at, records_synced
                FROM sync_runs
                WHERE source = c.source
                ORDER BY started_at DESC
                LIMIT 1
            ) r ON TRUE
            ORDER BY c.source
            """
        )
    return _serialize(rows)
