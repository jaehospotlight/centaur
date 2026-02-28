from __future__ import annotations

import time
from typing import Any

import structlog

from shared.engineer.models import EngineerResult, Phase
from shared.engineer.session import EngineerSession

log = structlog.get_logger()


def _import_agent_internals() -> tuple[Any, Any, Any, Any]:
    """Late import avoids module-level circular dependencies."""
    from api.agent import (
        _persist_session,
        _persist_turn,
        pop_session_state,
        set_session_state,
    )

    return set_session_state, pop_session_state, _persist_session, _persist_turn


class EngineerThreadBridge:
    """Adapter that registers engineer sessions in the threads API.

    Maps engineer phases to turns and tool calls to events so that
    the existing threads SSE stream picks them up automatically.
    """

    def __init__(self, thread_key: str, session: EngineerSession) -> None:
        self.thread_key = thread_key
        self.session = session
        self._current_turn: dict[str, Any] | None = None
        self._turn_counter = 0
        self._virtual_session: dict[str, Any] = {}

    def start(self) -> None:
        set_session_state, _, persist_session, _ = _import_agent_internals()
        now = time.time()
        self._virtual_session = {
            "container_id": self.session.run_id,
            "harness": "engineer",
            "agent_thread_id": self.session.run_id,
            "state": "working",
            "created_at": now,
            "last_activity": now,
            "turns": [],
            "thread_name": self.session.thread_name,
        }
        set_session_state(self.thread_key, self._virtual_session)
        persist_session(self._virtual_session, self.thread_key)

    async def start_phase(self, phase: Phase, label: str) -> None:
        prev_turn = self._current_turn
        if (
            self.session.thread_name
            and self._virtual_session.get("thread_name") != self.session.thread_name
        ):
            self._virtual_session["thread_name"] = self.session.thread_name
            _, _, persist_session, _ = _import_agent_internals()
            persist_session(self._virtual_session, self.thread_key)
        self._turn_counter += 1
        now = time.time()
        self._current_turn = {
            "turn_id": self._turn_counter,
            "user_message": f"[{phase.value}] {label}",
            "events": [],
            "result": "",
            "started_at": now,
            "finished_at": None,
            "exit_code": None,
            "timed_out": False,
            "duration_s": 0,
        }
        self._virtual_session["turns"].append(self._current_turn)
        self._virtual_session["last_activity"] = now
        self._virtual_session["state"] = "working"
        if prev_turn is not None:
            self._persist_finished_turn(prev_turn)

    async def on_event(self, event: dict[str, Any]) -> None:
        if self._current_turn is None:
            return
        self._current_turn["events"].append(event)
        self._virtual_session["last_activity"] = time.time()

    async def send_message(self, text: str) -> None:
        await self.on_event({"type": "raw", "text": text})

    def set_thread_name(self, name: str) -> None:
        self._virtual_session["thread_name"] = name
        self._virtual_session["last_activity"] = time.time()
        _, _, persist_session, _ = _import_agent_internals()
        persist_session(self._virtual_session, self.thread_key)

    def set_state(self, state: str) -> None:
        self._virtual_session["state"] = state
        self._virtual_session["last_activity"] = time.time()
        _, _, persist_session, _ = _import_agent_internals()
        persist_session(self._virtual_session, self.thread_key)

    async def on_waiting_for_reply(self, waiting: bool) -> None:
        """Set state to 'waiting' (True) or 'working' (False) for clarification UI."""
        self.set_state("waiting" if waiting else "working")

    def finalize(self, result: EngineerResult) -> None:
        if self._current_turn is not None:
            self._current_turn["result"] = result.pr_url or result.summary or result.error or ""
        self._finish_current_turn()
        state = "idle" if result.success else "error"
        self._virtual_session["state"] = state
        self._virtual_session["last_activity"] = time.time()
        _, _, persist_session, _ = _import_agent_internals()
        persist_session(self._virtual_session, self.thread_key)

    def cleanup(self) -> None:
        _, pop_session_state, _, _ = _import_agent_internals()
        pop_session_state(self.thread_key)

    def _finish_current_turn(self) -> None:
        if self._current_turn is None:
            return
        self._persist_finished_turn(self._current_turn)
        self._current_turn = None

    def _persist_finished_turn(self, turn: dict[str, Any]) -> None:
        now = time.time()
        turn["finished_at"] = now
        turn["duration_s"] = round(now - turn["started_at"], 1)
        _, _, _, persist_turn = _import_agent_internals()
        persist_turn(self.thread_key, turn)
