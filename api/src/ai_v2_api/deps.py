from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException, Request
from openai import AsyncOpenAI

from .config import settings


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_embedding_service(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> EmbeddingService:
    return EmbeddingService(pool=pool)


async def verify_api_key(
    x_api_key: Annotated[str, Header()],
) -> str:
    if not settings.api_secret_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


class EmbeddingService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed(self, text: str) -> list[float]:
        resp = await self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
        )
        return resp.data[0].embedding
