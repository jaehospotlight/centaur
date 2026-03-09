"""Internal endpoints served on control_net — no auth required.

Only the firewall can reach these because control_net is an internal
Docker network with only the API and firewall as members.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/injection-map")
async def injection_map(request: Request) -> dict:
    """Return the host→allowed_keys injection map for the firewall."""
    tm = request.app.state.tool_manager
    return tm.build_injection_map()
