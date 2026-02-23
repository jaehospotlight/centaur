from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog
from openai import AsyncOpenAI

from .models import EmbeddingRecord

log = structlog.get_logger()

EMBED_BATCH_SIZE = 2048


class EmbeddingService:
    def __init__(self, openai_api_key: str, model: str, dimensions: int) -> None:
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._model = model
        self._dimensions = dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            resp = await self._client.embeddings.create(
                input=batch,
                model=self._model,
                dimensions=self._dimensions,
            )
            all_embeddings.extend([d.embedding for d in resp.data])
        return all_embeddings

    async def embed_and_store(
        self, pool: asyncpg.Pool, records: list[EmbeddingRecord]
    ) -> int:
        if not records:
            return 0

        texts = [r.content for r in records]
        embeddings = await self.embed_texts(texts)

        stored = 0
        async with pool.acquire() as conn:
            for record, embedding in zip(records, embeddings):
                vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await conn.execute(
                    """
                    INSERT INTO embeddings (source, kind, source_id, content, embedding, metadata)
                    VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb)
                    ON CONFLICT (source, kind, source_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        created_at = now()
                    """,
                    record.source,
                    record.kind,
                    record.source_id,
                    record.content,
                    vec_str,
                    json.dumps(record.metadata),
                )
                stored += 1

        log.info("embeddings_stored", count=stored)
        return stored


async def hybrid_search(
    pool: asyncpg.Pool,
    query: str,
    embedding: list[float],
    limit: int = 20,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

    source_clause = ""
    args: list[Any] = [vec_str, query, limit]
    if source_filter:
        source_clause = "AND e.source = $4"
        args.append(source_filter)

    sql = f"""
    WITH vec AS (
        SELECT id, source, kind, source_id, content, metadata,
               1 - (embedding <=> $1::vector) AS vec_score,
               ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vec_rank
        FROM embeddings
        WHERE embedding IS NOT NULL {source_clause}
        ORDER BY embedding <=> $1::vector
        LIMIT $3 * 2
    ),
    fts AS (
        SELECT id, source, kind, source_id, content, metadata,
               ts_rank_cd(tsv, plainto_tsquery('english', $2)) AS fts_score,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', $2)) DESC
               ) AS fts_rank
        FROM embeddings
        WHERE tsv @@ plainto_tsquery('english', $2) {source_clause}
        ORDER BY fts_score DESC
        LIMIT $3 * 2
    ),
    combined AS (
        SELECT
            COALESCE(v.id, f.id) AS id,
            COALESCE(v.source, f.source) AS source,
            COALESCE(v.kind, f.kind) AS kind,
            COALESCE(v.source_id, f.source_id) AS source_id,
            COALESCE(v.content, f.content) AS content,
            COALESCE(v.metadata, f.metadata) AS metadata,
            COALESCE(v.vec_score, 0) AS vec_score,
            COALESCE(f.fts_score, 0) AS fts_score,
            -- RRF: Reciprocal Rank Fusion
            (1.0 / (60 + COALESCE(v.vec_rank, 1000))) +
            (1.0 / (60 + COALESCE(f.fts_rank, 1000))) AS rrf_score
        FROM vec v
        FULL OUTER JOIN fts f ON v.id = f.id
    )
    SELECT id, source, kind, source_id, content, metadata,
           vec_score, fts_score, rrf_score
    FROM combined
    ORDER BY rrf_score DESC
    LIMIT $3
    """

    rows = await pool.fetch(sql, *args)
    return [
        {
            "id": row["id"],
            "source": row["source"],
            "kind": row["kind"],
            "source_id": row["source_id"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"])
            if isinstance(row["metadata"], str)
            else row["metadata"],
            "vec_score": float(row["vec_score"]),
            "fts_score": float(row["fts_score"]),
            "rrf_score": float(row["rrf_score"]),
        }
        for row in rows
    ]
