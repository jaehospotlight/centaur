from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from .config import settings
from .mcp_server import mcp, set_pool
from .routers import health, query, search, secrets, sync

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("connecting to database", url=settings.database_url.split("@")[-1])
    pool = await asyncpg.create_pool(settings.database_url)
    app.state.pool = pool
    set_pool(pool)
    log.info("database pool created")
    yield
    await pool.close()
    log.info("database pool closed")


app = FastAPI(
    title="AI v2 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(query.router)
app.include_router(sync.router)
app.include_router(secrets.router)

app.mount("/mcp", app=mcp.streamable_http_app())
