#!/usr/bin/env python3
"""Generate embeddings for all records in the data plane.

Usage:
    python scripts/generate-embeddings.py \
        --database-url postgresql://tempo:tempo_prod@localhost:5432/ai_v2 \
        --openai-api-key sk-... \
        --batch-size 100
"""
import argparse
import asyncio
import json

import asyncpg
from openai import AsyncOpenAI


async def generate_embeddings(
    database_url: str,
    openai_api_key: str,
    model: str = "text-embedding-3-small",
    batch_size: int = 100,
):
    client = AsyncOpenAI(api_key=openai_api_key)
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=5)
    
    # Sources to embed with content extraction logic
    sources = [
        ("slack", "message", "data->>'text'"),
        ("slack", "thread", "data->>'all_text'"),
        ("github", "pull_request", "CONCAT(data->>'title', E'\\n', data->>'body')"),
        ("linear", "issue", "CONCAT(data->>'title', E'\\n', COALESCE(data->>'description', ''))"),
        ("linear", "comment", "data->>'body'"),
        ("granola", "meeting", "CONCAT(data->>'title', E'\\n', COALESCE(data->>'notes_plain', ''))"),
        ("gdrive", "doc", "CONCAT(data->>'name', E'\\n', COALESCE(data->>'content', ''))"),
        ("gcal", "event", "CONCAT(data->>'summary', E'\\n', COALESCE(data->>'description', ''))"),
        ("pylon", "message", "data->>'body'"),
        ("attio", "company", "CONCAT(data->>'name', E'\\n', COALESCE(data->>'description', ''))"),
    ]
    
    total_embedded = 0
    
    for source, kind, content_expr in sources:
        print(f"\n=== Embedding {source}/{kind} ===")
        
        # Get records not yet embedded
        async with pool.acquire() as pg:
            rows = await pg.fetch(f"""
                SELECT r.source, r.kind, r.external_id, {content_expr} AS content
                FROM raw_records r
                LEFT JOIN embeddings e ON e.source = r.source AND e.kind = r.kind AND e.source_id = r.external_id
                WHERE r.source = $1 AND r.kind = $2 AND e.id IS NULL
                  AND {content_expr} IS NOT NULL AND LENGTH({content_expr}) > 10
                ORDER BY r.fetched_at DESC
            """, source, kind)
        
        print(f"  {len(rows)} records to embed")
        
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            texts = [row["content"][:8000] for row in batch]  # Truncate to ~8k chars
            
            try:
                response = await client.embeddings.create(input=texts, model=model)
                embeddings = [e.embedding for e in response.data]
                
                async with pool.acquire() as pg:
                    await pg.executemany(
                        """INSERT INTO embeddings (source, kind, source_id, content, embedding)
                           VALUES ($1, $2, $3, $4, $5)
                           ON CONFLICT (source, kind, source_id) DO UPDATE SET
                             content = $4, embedding = $5, created_at = NOW()""",
                        [
                            (row["source"], row["kind"], row["external_id"],
                             row["content"][:8000], str(embeddings[j]))
                            for j, row in enumerate(batch)
                        ],
                    )
                
                total_embedded += len(batch)
                print(f"  {i + len(batch)}/{len(rows)} embedded")
            except Exception as e:
                print(f"  ERROR: {e}")
                continue
    
    await pool.close()
    print(f"\n=== Done: {total_embedded} total embeddings generated ===")


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for ai_v2")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--openai-api-key", required=True)
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    
    asyncio.run(generate_embeddings(args.database_url, args.openai_api_key, args.model, args.batch_size))


if __name__ == "__main__":
    main()
