from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()


@dataclass
class Model:
    name: str
    sql: str
    materialized: str  # "table", "view", or "matview"
    depends_on: list[str]
    indexes: list[str]


@dataclass
class TransformResult:
    models_run: int
    duration_ms: int


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    lines = content.split("\n")
    name = ""
    materialized = "table"
    depends_on: list[str] = []
    indexes: list[str] = []
    in_indexes = False
    sql_start = 0

    for i, line in enumerate(lines):
        trimmed = line.strip()
        if not trimmed.startswith("--"):
            sql_start = i
            break

        stripped = trimmed[2:].strip()

        if stripped.startswith("model:"):
            name = stripped[len("model:") :].strip()
            in_indexes = False
        elif stripped.startswith("materialized:"):
            val = stripped[len("materialized:") :].strip()
            materialized = val if val in ("view", "matview") else "table"
            in_indexes = False
        elif stripped.startswith("depends_on:"):
            val = stripped[len("depends_on:") :].strip()
            if val:
                depends_on.extend(d.strip() for d in val.split(",") if d.strip())
            in_indexes = False
        elif stripped.startswith("indexes:"):
            in_indexes = True
        elif in_indexes and stripped.startswith("- "):
            indexes.append(stripped[2:].strip())
        elif in_indexes and not stripped.startswith("-"):
            in_indexes = False

    sql = "\n".join(lines[sql_start:]).strip()
    meta = {
        "name": name,
        "materialized": materialized,
        "depends_on": depends_on,
        "indexes": indexes,
    }
    return meta, sql


def load_sql_models(sql_dir: str | Path) -> list[Model]:
    sql_path = Path(sql_dir)
    models: list[Model] = []

    for subdir in ("staging", "marts"):
        d = sql_path / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.sql")):
            content = f.read_text()
            meta, sql = parse_frontmatter(content)
            if not meta["name"]:
                log.warning("sql_model_no_name", file=str(f))
                continue
            models.append(
                Model(
                    name=meta["name"],
                    sql=sql,
                    materialized=meta["materialized"],
                    depends_on=meta["depends_on"],
                    indexes=meta["indexes"],
                )
            )

    return models


def topo_sort(models: list[Model]) -> list[Model]:
    by_name = {m.name: m for m in models}
    sorted_models: list[Model] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError(f"Cycle detected at model: {name}")
        visiting.add(name)

        model = by_name.get(name)
        if model is None:
            raise ValueError(f"Unknown dependency: {name}")

        for dep in model.depends_on:
            if dep in by_name:
                visit(dep)

        visiting.discard(name)
        visited.add(name)
        sorted_models.append(model)

    for model in models:
        visit(model.name)

    return sorted_models


async def run_transform(
    pool: asyncpg.Pool, sql_dir: str | Path
) -> TransformResult:
    models = load_sql_models(sql_dir)
    if not models:
        log.info("no_sql_models_found", sql_dir=str(sql_dir))
        return TransformResult(models_run=0, duration_ms=0)

    sorted_models = topo_sort(models)
    start = time.monotonic()
    count = 0

    async with pool.acquire() as conn:
        for model in sorted_models:
            log.info("running_model", name=model.name, type=model.materialized)

            # Drop existing object
            await conn.execute(
                f'DROP MATERIALIZED VIEW IF EXISTS "{model.name}" CASCADE'
            )
            await conn.execute(f'DROP VIEW IF EXISTS "{model.name}" CASCADE')
            await conn.execute(f'DROP TABLE IF EXISTS "{model.name}" CASCADE')

            if model.materialized == "view":
                await conn.execute(
                    f'CREATE VIEW "{model.name}" AS {model.sql}'
                )
            elif model.materialized == "matview":
                await conn.execute(
                    f'CREATE MATERIALIZED VIEW "{model.name}" AS {model.sql}'
                )
            else:
                await conn.execute(
                    f'CREATE TABLE "{model.name}" AS {model.sql}'
                )

            # Create indexes
            for idx_sql in model.indexes:
                # Replace model name placeholder if needed
                idx = idx_sql.replace("{table}", model.name)
                await conn.execute(idx)

            count += 1

    duration = int((time.monotonic() - start) * 1000)
    log.info("transform_done", models_run=count, duration_ms=duration)
    return TransformResult(models_run=count, duration_ms=duration)
