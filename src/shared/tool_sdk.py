"""Tool SDK — what tool authors import."""

from __future__ import annotations

import contextlib
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import quote

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    name: str
    secrets: dict[str, str] = field(default_factory=dict)


_tool_ctx: ContextVar[ToolContext] = ContextVar("_tool_ctx")


def set_tool_context(ctx: ToolContext) -> Any:
    return _tool_ctx.set(ctx)


def reset_tool_context(token: Any) -> None:
    _tool_ctx.reset(token)


def get_tool_context() -> ToolContext:
    return _tool_ctx.get()


# ---------------------------------------------------------------------------
# Secret Manager backend (replaces direct 1Password CLI calls)
# ---------------------------------------------------------------------------

_SECRET_MANAGER_URL = os.environ.get("SECRET_MANAGER_URL", "")

# Local cache so we don't HTTP on every secret() call.
_sm_cache: dict[str, tuple[str, float]] = {}
_sm_cache_lock = Lock()
_SM_CACHE_TTL = 60  # re-check every 60s (the sidecar itself refreshes from 1PW)


def _sm_read(key: str) -> str | None:
    """Fetch a secret from the secret-manager sidecar. Cached locally."""
    if not _SECRET_MANAGER_URL:
        return None

    now = monotonic()
    with _sm_cache_lock:
        cached = _sm_cache.get(key)
        if cached is not None:
            value, expiry = cached
            if now < expiry:
                return value
            del _sm_cache[key]

    try:
        import httpx

        resp = httpx.get(f"{_SECRET_MANAGER_URL}/secrets/{quote(key, safe='')}", timeout=5.0)
        if resp.status_code != 200:
            return None
        value = resp.json()["value"]
    except Exception:
        log.debug("secret-manager fetch failed for %s", key)
        return None

    with _sm_cache_lock:
        _sm_cache[key] = (value, monotonic() + _SM_CACHE_TTL)
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def secret(key: str, default: str | None = None) -> str:
    """Get a secret. Resolution order: tool context → secret manager → os.environ.

    - **ToolContext**: Set by ToolManager, populated from .env files (if any).
    - **Secret Manager**: HTTP sidecar backed by 1Password (``SECRET_MANAGER_URL``).
    - **os.environ**: Final fallback for local dev, Docker env, k8s, etc.
    """
    # 1. Check tool context if available (server mode)
    try:
        ctx = _tool_ctx.get()
        val = ctx.secrets.get(key)
        if val is not None:
            return val
    except LookupError:
        pass

    # 2. Secret manager sidecar (backed by 1Password)
    val = _sm_read(key)
    if val is not None:
        return val

    # 3. Fall back to os.environ (local dev, Docker, k8s)
    val = os.environ.get(key)
    if val is not None:
        return val

    if default is not None:
        return default

    ctx_name = ""
    with contextlib.suppress(LookupError):
        ctx_name = f" for tool '{_tool_ctx.get().name}'"
    raise KeyError(f"Missing secret '{key}'{ctx_name}")
