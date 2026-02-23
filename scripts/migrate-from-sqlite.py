#!/usr/bin/env python3
"""Migrate data from metronome SQLite (pov.db) to ai_v2 Postgres.

Usage:
    python scripts/migrate-from-sqlite.py \
        --sqlite-path ~/.pov/pov.db \
        --database-url postgresql://tempo:tempo_prod@localhost:5432/ai_v2 \
        --batch-size 5000
"""
import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time

import asyncpg


async def migrate(sqlite_path: str, database_url: str, batch_size: int = 5000):
    print(f"Connecting to SQLite: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    
    print(f"Connecting to Postgres: {database_url}")
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    
    # 1. Migrate raw_records
    total = conn.execute("SELECT COUNT(*) FROM raw__records").fetchone()[0]
    print(f"\n=== Migrating raw_records: {total:,} rows ===")
    
    cursor = conn.execute(
        "SELECT source, kind, external_id, fetched_at, content_hash, data FROM raw__records"
    )
    
    migrated = 0
    batch = []
    
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        
        for row in rows:
            batch.append((
                row["source"], row["kind"], row["external_id"],
                row["fetched_at"], row["content_hash"], row["data"]
            ))
        
        async with pool.acquire() as pg:
            await pg.executemany(
                """INSERT INTO raw_records (source, kind, external_id, fetched_at, content_hash, data)
                   VALUES ($1, $2, $3, $4::timestamptz, $5, $6::jsonb)
                   ON CONFLICT (source, kind, external_id, content_hash) DO NOTHING""",
                batch,
            )
        
        migrated += len(batch)
        pct = (migrated / total) * 100
        print(f"  {migrated:,}/{total:,} ({pct:.1f}%)")
        batch = []
    
    # 2. Migrate sync_cursors
    cursor_rows = conn.execute("SELECT * FROM sync_cursors").fetchall()
    print(f"\n=== Migrating sync_cursors: {len(cursor_rows)} rows ===")
    async with pool.acquire() as pg:
        for row in cursor_rows:
            await pg.execute(
                """INSERT INTO sync_cursors (cursor_key, source, kind, entity_id, cursor, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6::timestamptz)
                   ON CONFLICT (cursor_key) DO UPDATE SET cursor = $5, updated_at = $6::timestamptz""",
                row["cursor_key"], row["source"], row["kind"],
                row.get("entity_id"), row["cursor"], row["updated_at"],
            )
    
    # 3. Migrate people
    people_rows = conn.execute("SELECT * FROM people").fetchall()
    print(f"\n=== Migrating people: {len(people_rows)} rows ===")
    async with pool.acquire() as pg:
        for row in people_rows:
            await pg.execute(
                """INSERT INTO people (slug, name, email, role, is_direct_report, focus_area)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (slug) DO UPDATE SET
                     name = $2, email = $3, role = $4, is_direct_report = $5, focus_area = $6""",
                row["slug"], row["name"], row.get("email"),
                row.get("role"), bool(row.get("is_direct_report", 0)),
                row.get("focus_area"),
            )
    
    # 4. Migrate entity_mappings
    mapping_rows = conn.execute("SELECT * FROM entity_mappings").fetchall()
    print(f"\n=== Migrating entity_mappings: {len(mapping_rows)} rows ===")
    async with pool.acquire() as pg:
        for row in mapping_rows:
            await pg.execute(
                """INSERT INTO entity_mappings (source, external_id, person_slug)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (source, external_id) DO NOTHING""",
                row["source"], row["external_id"], row["person_slug"],
            )
    
    # 5. Migrate enrichment_feedback if exists
    try:
        ef_rows = conn.execute("SELECT * FROM enrichment_feedback").fetchall()
        print(f"\n=== Migrating enrichment_feedback: {len(ef_rows)} rows ===")
        async with pool.acquire() as pg:
            for row in ef_rows:
                await pg.execute(
                    """INSERT INTO enrichment_feedback (source, entity_id, action, reason, created_by, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6::timestamptz)
                       ON CONFLICT (source, entity_id) DO NOTHING""",
                    row["source"], row["entity_id"], row["action"],
                    row.get("reason"), row.get("created_by"), row["created_at"],
                )
    except sqlite3.OperationalError:
        print("  (enrichment_feedback table not found, skipping)")
    
    await pool.close()
    conn.close()
    
    print(f"\n=== Migration complete! ===")
    print(f"  raw_records: {migrated:,}")
    print(f"  sync_cursors: {len(cursor_rows)}")
    print(f"  people: {len(people_rows)}")
    print(f"  entity_mappings: {len(mapping_rows)}")


def main():
    parser = argparse.ArgumentParser(description="Migrate metronome SQLite to Postgres")
    parser.add_argument("--sqlite-path", required=True, help="Path to pov.db")
    parser.add_argument("--database-url", required=True, help="Postgres connection URL")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for inserts")
    args = parser.parse_args()
    
    asyncio.run(migrate(args.sqlite_path, args.database_url, args.batch_size))


if __name__ == "__main__":
    main()
