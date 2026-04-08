"""Workflow: recurring agent loop with configurable interval and deadline.

Lets agents self-schedule durable polling/monitoring tasks.  A sandbox
agent creates a run of this workflow via POST /workflows/runs with input
like:

    {
        "thread_key": "slack:C042WDDP89Y:1773364194.179929",
        "prompt": "Check if CI job https://… has finished. If yes, reply
                   with the result and set done=true. If not, say still
                   running.",
        "interval_seconds": 300,
        "max_iterations": 288,
        "deadline_seconds": 86400,
        "delivery": { "channel": "C042WDDP89Y", ... }
    }

Each iteration runs a full agent turn with the prompt (plus iteration
context).  The loop terminates when:
  - the agent result contains "done":true (JSON) or the literal DONE
  - max_iterations is reached
  - deadline_seconds elapses
  - the workflow is cancelled externally
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from api.runtime_control import ControlPlaneError
from api.workflow_engine import Delivery, WorkflowContext

WORKFLOW_NAME = "agent_loop"

_DEFAULT_INTERVAL_S = 300  # 5 min
_DEFAULT_MAX_ITERATIONS = 288  # 5 min × 288 = 24h
_DEFAULT_DEADLINE_S = 86_400  # 24h
_MAX_DEADLINE_S = 7 * 86_400  # 7 days hard cap


@dataclass
class Input:
    thread_key: str = ""
    prompt: str = ""
    interval_seconds: int = _DEFAULT_INTERVAL_S
    max_iterations: int = _DEFAULT_MAX_ITERATIONS
    deadline_seconds: int = _DEFAULT_DEADLINE_S
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    delivery: Delivery = field(default_factory=Delivery)
    prompt_selector: str | None = None
    agents_md_override: str | None = None


def _iteration_prompt(prompt: str, iteration: int, max_iterations: int) -> str:
    return (
        f"{prompt}\n\n"
        f"---\n"
        f"Iteration {iteration}/{max_iterations}.  "
        f"If the task is complete, include the JSON `{{\"done\": true}}` "
        f"in your response.  Otherwise just report current status."
    )


def _is_done(result: dict[str, Any]) -> bool:
    """Check if the agent signalled completion."""
    execution = result.get("execution") or {}
    result_text = str(execution.get("result_text") or "")
    if not result_text:
        return False

    # Check for literal JSON {"done": true} anywhere in the result
    try:
        parsed = json.loads(result_text)
        if isinstance(parsed, dict) and parsed.get("done") is True:
            return True
    except (json.JSONDecodeError, ValueError):
        pass

    # Check for {"done": true} embedded in prose
    if '"done"' in result_text and "true" in result_text:
        try:
            # Find JSON object boundaries
            for i, ch in enumerate(result_text):
                if ch == "{":
                    depth = 1
                    for j in range(i + 1, len(result_text)):
                        if result_text[j] == "{":
                            depth += 1
                        elif result_text[j] == "}":
                            depth -= 1
                            if depth == 0:
                                fragment = json.loads(result_text[i : j + 1])
                                if isinstance(fragment, dict) and fragment.get("done") is True:
                                    return True
                                break
        except (json.JSONDecodeError, ValueError):
            pass

    return False


async def handler(inp: Input, ctx: WorkflowContext) -> dict[str, Any]:
    """Run an agent turn in a loop with sleeps between iterations."""
    from api.workflow_engine import do_agent_turn, text_part

    if not inp.thread_key.strip():
        raise ControlPlaneError(
            "INVALID_WORKFLOW_INPUT",
            "agent_loop requires thread_key",
            422,
        )
    if not inp.prompt.strip():
        raise ControlPlaneError(
            "INVALID_WORKFLOW_INPUT",
            "agent_loop requires prompt",
            422,
        )

    interval = max(inp.interval_seconds, 10)  # floor: 10s
    deadline_s = min(max(inp.deadline_seconds, 60), _MAX_DEADLINE_S)
    max_iter = max(inp.max_iterations, 1)
    thread_key = inp.thread_key.strip()

    started_at = await ctx.step(
        "started_at",
        lambda: dt.datetime.now(dt.timezone.utc).isoformat(),
        step_kind="gather",
    )
    deadline = dt.datetime.fromisoformat(started_at) + dt.timedelta(seconds=deadline_s)

    last_result: dict[str, Any] = {}
    completed_iterations = 0

    for iteration in range(1, max_iter + 1):
        if dt.datetime.now(dt.timezone.utc) >= deadline:
            ctx.log("agent_loop_deadline", thread_key=thread_key, iteration=iteration)
            return {
                "status": "deadline",
                "iterations": completed_iterations,
                "last_result": last_result,
            }

        iter_prompt = _iteration_prompt(inp.prompt, iteration, max_iter)
        last_result = await do_agent_turn(
            ctx,
            thread_key=thread_key,
            parts=[text_part(iter_prompt)],
            user_id=inp.user_id,
            metadata={
                **inp.metadata,
                "source": "agent_loop",
                "iteration": iteration,
                "max_iterations": max_iter,
            },
            delivery=inp.delivery,
            prompt_selector=inp.prompt_selector,
            agents_md_override=inp.agents_md_override,
        )
        completed_iterations = iteration

        if _is_done(last_result):
            ctx.log("agent_loop_done", thread_key=thread_key, iteration=iteration)
            return {
                "status": "done",
                "iterations": iteration,
                "last_result": last_result,
            }

        # Sleep before next iteration (skip after last)
        if iteration < max_iter:
            await ctx.sleep(f"wait_{iteration}", dt.timedelta(seconds=interval))

    return {
        "status": "max_iterations",
        "iterations": completed_iterations,
        "last_result": last_result,
    }
