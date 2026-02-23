from __future__ import annotations

from datetime import date
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_pool, verify_api_key

router = APIRouter(prefix="/api/query", dependencies=[Depends(verify_api_key)])


@router.get("/slack/messages")
async def slack_messages(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    channel: str | None = None,
    user: str | None = None,
    after: date | None = None,
    before: date | None = None,
    text: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions: list[str] = []
    args: list = []
    idx = 1

    if channel:
        conditions.append(f"channel = ${idx}")
        args.append(channel)
        idx += 1
    if user:
        conditions.append(f"user_name = ${idx}")
        args.append(user)
        idx += 1
    if after:
        conditions.append(f"ts >= ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"ts <= ${idx}")
        args.append(before)
        idx += 1
    if text:
        conditions.append(f"content ILIKE ${idx}")
        args.append(f"%{text}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    args.extend([limit, offset])

    sql = f"""
    SELECT id, channel, user_name, content, ts, thread_ts, metadata
    FROM slack_messages
    {where}
    ORDER BY ts DESC
    LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


@router.get("/slack/threads")
async def slack_threads(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    channel: str | None = None,
    after: date | None = None,
    before: date | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions: list[str] = []
    args: list = []
    idx = 1

    if channel:
        conditions.append(f"channel = ${idx}")
        args.append(channel)
        idx += 1
    if after:
        conditions.append(f"ts >= ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"ts <= ${idx}")
        args.append(before)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    args.extend([limit, offset])

    sql = f"""
    SELECT thread_ts, channel, reply_count, participants, ts, last_reply_at, metadata
    FROM slack_threads
    {where}
    ORDER BY last_reply_at DESC
    LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


@router.get("/linear/issues")
async def linear_issues(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    team: str | None = None,
    assignee: str | None = None,
    state: str | None = None,
    label: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions: list[str] = []
    args: list = []
    idx = 1

    if team:
        conditions.append(f"team = ${idx}")
        args.append(team)
        idx += 1
    if assignee:
        conditions.append(f"assignee = ${idx}")
        args.append(assignee)
        idx += 1
    if state:
        conditions.append(f"state = ${idx}")
        args.append(state)
        idx += 1
    if label:
        conditions.append(f"${idx} = ANY(labels)")
        args.append(label)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    args.extend([limit, offset])

    sql = f"""
    SELECT id, identifier, title, state, assignee, team, labels, priority,
           created_at, updated_at, metadata
    FROM linear_issues
    {where}
    ORDER BY updated_at DESC
    LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


@router.get("/github/prs")
async def github_prs(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    repo: str | None = None,
    author: str | None = None,
    state: str | None = None,
    after: date | None = None,
    before: date | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions: list[str] = []
    args: list = []
    idx = 1

    if repo:
        conditions.append(f"repo = ${idx}")
        args.append(repo)
        idx += 1
    if author:
        conditions.append(f"author = ${idx}")
        args.append(author)
        idx += 1
    if state:
        conditions.append(f"state = ${idx}")
        args.append(state)
        idx += 1
    if after:
        conditions.append(f"created_at >= ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"created_at <= ${idx}")
        args.append(before)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    args.extend([limit, offset])

    sql = f"""
    SELECT id, number, title, state, author, repo, created_at, merged_at,
           additions, deletions, metadata
    FROM github_prs
    {where}
    ORDER BY created_at DESC
    LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


@router.get("/timeline")
async def timeline(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    days: int = Query(default=7, ge=1, le=90),
    source: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions = [f"occurred_at >= NOW() - INTERVAL '{days} days'"]
    args: list = []
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
    args.extend([limit, offset])

    sql = f"""
    SELECT id, source, event_type, actor, summary, occurred_at, url, metadata
    FROM activity_timeline
    {where}
    ORDER BY occurred_at DESC
    LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


@router.get("/people")
async def list_people(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, display_name, emails, slack_id, github_username,
                   linear_id, metadata
            FROM people
            ORDER BY display_name
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [dict(r) for r in rows]


@router.get("/people/{slug}")
async def get_person(
    slug: str,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
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
            raise HTTPException(status_code=404, detail="Person not found")

        recent_activity = await conn.fetch(
            """
            SELECT source, event_type, summary, occurred_at, url
            FROM activity_timeline
            WHERE actor = $1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
            slug,
        )

    return {
        **dict(person),
        "recent_activity": [dict(r) for r in recent_activity],
    }
