from __future__ import annotations

import re
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import EmbeddingService, get_embedding_service, get_pool, verify_api_key

router = APIRouter(prefix="/api/search", dependencies=[Depends(verify_api_key)])

DISALLOWED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class SearchRequest(BaseModel):
    query: str
    sources: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchResult(BaseModel):
    score: float
    source: str
    content: str
    metadata: dict
    url: str | None = None


class SqlQueryRequest(BaseModel):
    query: str


@router.post("")
async def search(
    body: SearchRequest,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    embedding_svc: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> list[SearchResult]:
    embedding = await embedding_svc.embed(body.query)
    embedding_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    source_filter = ""
    args: list = [body.query, body.limit]
    if body.sources:
        placeholders = ",".join(f"${i + 3}" for i in range(len(body.sources)))
        source_filter = f"AND source IN ({placeholders})"
        args.extend(body.sources)

    sql = f"""
    WITH vector_results AS (
        SELECT id, source, content, metadata, url,
               1 - (embedding <=> '{embedding_literal}'::vector) AS vector_score,
               ROW_NUMBER() OVER (ORDER BY embedding <=> '{embedding_literal}'::vector) AS vector_rank
        FROM documents
        WHERE embedding IS NOT NULL {source_filter}
        ORDER BY embedding <=> '{embedding_literal}'::vector
        LIMIT $2
    ),
    fts_results AS (
        SELECT id, source, content, metadata, url,
               ts_rank_cd(search_vector, plainto_tsquery('english', $1)) AS fts_score,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank_cd(search_vector, plainto_tsquery('english', $1)) DESC
               ) AS fts_rank
        FROM documents
        WHERE search_vector @@ plainto_tsquery('english', $1) {source_filter}
        ORDER BY fts_score DESC
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

    return [
        SearchResult(
            score=float(r["score"]),
            source=r["source"],
            content=r["content"],
            metadata=dict(r["metadata"]) if r["metadata"] else {},
            url=r["url"],
        )
        for r in rows
    ]


@router.post("/sql")
async def sql_query(
    body: SqlQueryRequest,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[dict]:
    if DISALLOWED_SQL.search(body.query):
        raise HTTPException(status_code=400, detail="Only read-only queries are allowed")

    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(body.query)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return [dict(r) for r in rows]


@router.get("/sources")
async def list_sources(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, COUNT(*) AS record_count
            FROM documents
            GROUP BY source
            ORDER BY source
            """
        )
    return [{"source": r["source"], "record_count": r["record_count"]} for r in rows]
