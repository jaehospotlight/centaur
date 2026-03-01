"""Secret Manager — cached mirror of 1Password secrets.

A lightweight sidecar service that loads all secrets from a 1Password vault
on startup and serves them over HTTP.  Other services (API, ETL) query this
instead of talking to 1Password directly, so they can restart without
re-fetching.

Uses the official 1Password Python SDK with a service account token.
The SDK maintains its own authenticated session and refreshes it
automatically — no CLI or manual signin needed.

Requires ``OP_SERVICE_ACCOUNT_TOKEN`` in the environment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from onepassword.client import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("secret_manager")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_VAULT_NAME = os.environ.get("OP_VAULT", "ai-agents")
_REFRESH_INTERVAL = int(os.environ.get("SECRET_REFRESH_SECONDS", "300"))  # 5 min

# In-memory cache: key → value
_cache: dict[str, str] = {}

# SDK client — initialised once at startup
_client: Client | None = None


# ---------------------------------------------------------------------------
# 1Password SDK helpers
# ---------------------------------------------------------------------------


def _normalize(title: str) -> str:
    """Convert a human-readable title to an ENV_VAR_NAME."""
    return re.sub(r"[^A-Z0-9]", "_", title.upper()).strip("_")


async def _init_client() -> Client:
    """Create and authenticate a 1Password SDK client."""
    token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "")
    if not token:
        raise RuntimeError("OP_SERVICE_ACCOUNT_TOKEN is not set")
    return await Client.authenticate(
        auth=token,
        integration_name="ai-v2-secret-manager",
        integration_version="1.0.0",
    )


async def _find_vault_id(client: Client, name: str) -> str:
    """Find a vault ID by name."""
    vaults = await client.vaults.list_all()
    async for v in vaults:
        if v.title == name:
            return v.id
    raise RuntimeError(f"Vault '{name}' not found")


async def _load_all() -> int:
    """Fetch every item from the vault and populate the cache.

    Returns the number of secrets loaded.
    """
    global _client, _cache
    if _client is None:
        _client = await _init_client()

    vault_id = await _find_vault_id(_client, _VAULT_NAME)
    items = await _client.items.list_all(vault_id)

    new_cache: dict[str, str] = {}
    async for item_overview in items:
        ref = f"op://{_VAULT_NAME}/{item_overview.id}/password"
        try:
            value = await _client.secrets.resolve(ref)
        except Exception:
            # Try 'credential' field for API_CREDENTIAL items
            try:
                ref_alt = f"op://{_VAULT_NAME}/{item_overview.id}/credential"
                value = await _client.secrets.resolve(ref_alt)
            except Exception:
                log.debug("skipping item %s — no password/credential field", item_overview.title)
                continue

        if not value:
            continue

        title = item_overview.title
        new_cache[title] = value
        norm = _normalize(title)
        if norm != title:
            new_cache[norm] = value

    # Atomic swap — avoids readers seeing an empty cache during refresh
    _cache = new_cache
    log.info("loaded %d keys from vault '%s'", len(_cache), _VAULT_NAME)
    return len(_cache)


# ---------------------------------------------------------------------------
# Background refresh
# ---------------------------------------------------------------------------


async def _refresh_loop() -> None:
    while True:
        await asyncio.sleep(_REFRESH_INTERVAL)
        try:
            await _load_all()
        except Exception:
            log.exception("refresh failed")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info("loading secrets from vault '%s' ...", _VAULT_NAME)
    await _load_all()
    task = asyncio.create_task(_refresh_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Secret Manager", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cached_keys": len(_cache)}


@app.get("/secrets/{key}")
def get_secret(key: str) -> dict:
    value = _cache.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"value": value}
