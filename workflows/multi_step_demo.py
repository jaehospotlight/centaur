"""Workflow: multi-step demo with branching and loops."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from api.workflow_engine import WorkflowContext

WORKFLOW_NAME = "multi_step_demo"


@dataclass
class Input:
    message: str = "hello"
    items: list[str] = field(default_factory=lambda: ["alpha", "bravo", "charlie"])


async def handler(inp: Input, ctx: WorkflowContext) -> dict[str, Any]:
    """Demo workflow exercising step replay, loops, and conditionals."""

    # Step 1: gather input
    greeting = await ctx.step(
        "gather",
        lambda: {
            "message": inp.message,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        step_kind="gather",
    )

    # Step 2: transform — uses result from step 1
    transformed = await ctx.step(
        "transform",
        lambda: {
            "upper": greeting["message"].upper(),
            "length": len(greeting["message"]),
        },
        step_kind="transform",
    )

    # Step 3: loop — process items (demonstrates name deduplication)
    results = []
    for item in inp.items:
        val = item  # capture for lambda
        result = await ctx.step(
            "process_item",
            lambda: {"item": val, "processed": True},
            step_kind="loop_item",
        )
        results.append(result)

    # Step 4: conditional branch
    if transformed["length"] > 10:
        branch = await ctx.step(
            "long_message_branch",
            lambda: {"branch": "long", "action": "summarized"},
            step_kind="branch",
        )
    else:
        branch = await ctx.step(
            "short_message_branch",
            lambda: {"branch": "short", "action": "padded"},
            step_kind="branch",
        )

    return {
        "greeting": greeting,
        "transformed": transformed,
        "loop_results": results,
        "branch": branch,
    }
