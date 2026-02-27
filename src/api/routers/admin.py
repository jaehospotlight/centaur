from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from api.deps import verify_api_key

log = structlog.get_logger()

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_api_key)])


@router.post("/reload-plugins")
async def reload_plugins(request: Request) -> dict:
    """Hot-reload all plugins without restarting the API server."""
    plugin_manager = request.app.state.plugin_manager
    result = await run_in_threadpool(plugin_manager.reload)
    log.info("plugins_reloaded", **result)
    return result
