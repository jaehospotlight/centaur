"""Pre-warmed container pool — keeps N containers ready with stdin sockets open.

Eliminates container startup latency (~15s) by maintaining a pool of idle
containers that can be instantly claimed when a new thread arrives.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from dataclasses import dataclass, field

import structlog

from api.pipe_agent import (
    PipeSession,
    _create_container,
    _docker_client,
)

log = structlog.get_logger()

# Pool configuration
POOL_SIZE = int(os.getenv("WARM_POOL_SIZE", "5"))
POOL_HARNESS = os.getenv("WARM_POOL_HARNESS", "amp")
POOL_REPLENISH_INTERVAL = float(os.getenv("WARM_POOL_REPLENISH_INTERVAL", "5.0"))


@dataclass
class WarmContainer:
    """A pre-warmed container not yet bound to any thread."""
    container_id: str
    harness: str
    engine: str
    created_at: float = field(default_factory=time.time)


# Thread-safe pool (accessed from async + sync contexts)
_pool_lock = threading.Lock()
_pool: list[WarmContainer] = []
_replenish_task: asyncio.Task | None = None


def pool_size() -> int:
    """Current number of warm containers ready."""
    with _pool_lock:
        return len(_pool)


def pool_status() -> dict:
    """Return pool diagnostics."""
    with _pool_lock:
        containers = [
            {"container_id": w.container_id[:12], "age_s": round(time.time() - w.created_at, 1)}
            for w in _pool
        ]
    return {
        "target_size": POOL_SIZE,
        "current_size": len(containers),
        "harness": POOL_HARNESS,
        "containers": containers,
    }


def _spawn_warm_container() -> WarmContainer | None:
    """Synchronously create one warm container. Returns None on failure."""
    engines = {"amp": "amp", "claude-code": "claude-code", "codex": "codex"}
    engine = engines.get(POOL_HARNESS, "amp")

    # Use a unique placeholder thread key — will be relabeled on claim
    placeholder_key = f"warm-{int(time.time() * 1000)}-{id(threading.current_thread())}"
    try:
        client = _docker_client()
        container = _create_container(client, placeholder_key, POOL_HARNESS, engine, warm=True)

        warm = WarmContainer(
            container_id=container.id,
            harness=POOL_HARNESS,
            engine=engine,
        )
        log.info("warm_container_created", container=container.id[:12])
        return warm
    except Exception as exc:
        log.warning("warm_container_spawn_failed", error=str(exc))
        return None


def _replenish_sync() -> int:
    """Spawn containers until the pool reaches target size. Returns count spawned."""
    spawned = 0
    while True:
        with _pool_lock:
            deficit = POOL_SIZE - len(_pool)
        if deficit <= 0:
            break
        warm = _spawn_warm_container()
        if warm is None:
            break
        with _pool_lock:
            _pool.append(warm)
        spawned += 1
    return spawned


def claim_container(thread_key: str, harness: str = "amp") -> PipeSession | None:
    """Try to claim a warm container from the pool. Returns PipeSession or None.

    Only returns a container if the requested harness matches the pool harness.
    """
    if harness != POOL_HARNESS:
        return None

    warm: WarmContainer | None = None
    with _pool_lock:
        if _pool:
            warm = _pool.pop(0)

    if warm is None:
        return None

    # Verify container is still running
    try:
        client = _docker_client()
        container = client.containers.get(warm.container_id)
        if container.status != "running":
            log.warning("warm_container_dead_on_claim", container=warm.container_id[:12])
            with contextlib.suppress(Exception):
                container.remove(force=True)
            return None
    except Exception:
        return None

    # Rename container to match the thread key
    new_name = f"pipe-{thread_key.replace(':', '-').replace('.', '-')[:40]}"
    with contextlib.suppress(Exception):
        container.rename(new_name)

    session = PipeSession(
        container_id=warm.container_id,
        thread_key=thread_key,
        harness=harness,
        engine=warm.engine,
        started_at=time.time(),
    )
    log.info(
        "warm_container_claimed",
        thread_key=thread_key,
        container=warm.container_id[:12],
        pool_age_s=round(time.time() - warm.created_at, 1),
    )
    return session


def _cleanup_pool_sync() -> int:
    """Stop and remove all warm containers. Returns count cleaned."""
    with _pool_lock:
        to_clean = list(_pool)
        _pool.clear()
    cleaned = 0
    client = _docker_client()
    for warm in to_clean:
        with contextlib.suppress(Exception):
            c = client.containers.get(warm.container_id)
            c.stop(timeout=3)
            c.remove()
            cleaned += 1
    return cleaned


# ── Async API ────────────────────────────────────────────────────────────────


async def replenish() -> int:
    """Async wrapper — spawn missing warm containers."""
    return await asyncio.to_thread(_replenish_sync)


async def cleanup_pool() -> int:
    """Async wrapper — tear down all warm containers."""
    return await asyncio.to_thread(_cleanup_pool_sync)


def _recover_warm_sync() -> int:
    """Recover existing warm containers from Docker on API restart."""
    client = _docker_client()
    recovered = 0
    try:
        containers = client.containers.list(filters={"label": "ai2.warm=true"})
    except Exception:
        return 0
    for container in containers:
        if container.status != "running":
            with contextlib.suppress(Exception):
                container.remove(force=True)
            continue
        with _pool_lock:
            # Don't exceed target
            if len(_pool) >= POOL_SIZE:
                break
            _pool.append(
                WarmContainer(
                    container_id=container.id,
                    harness=container.labels.get("ai2.harness", POOL_HARNESS),
                    engine=container.labels.get("ai2.engine", "amp"),
                )
            )
            recovered += 1
    return recovered


async def start_replenish_loop() -> asyncio.Task:
    """Start a background task that keeps the pool at target size."""
    global _replenish_task

    async def _loop() -> None:
        # Recover any surviving warm containers from a previous run
        recovered = await asyncio.to_thread(_recover_warm_sync)
        if recovered:
            log.info("warm_pool_recovered", recovered=recovered)
        # Fill the rest
        count = await replenish()
        if count:
            log.info("warm_pool_initial_fill", spawned=count, target=POOL_SIZE)
        while True:
            await asyncio.sleep(POOL_REPLENISH_INTERVAL)
            try:
                await replenish()
            except Exception as exc:
                log.warning("warm_pool_replenish_error", error=str(exc))

    _replenish_task = asyncio.create_task(_loop())
    return _replenish_task


async def stop_replenish_loop() -> None:
    """Cancel replenish loop and drain the pool."""
    global _replenish_task
    if _replenish_task:
        _replenish_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _replenish_task
        _replenish_task = None
    cleaned = await cleanup_pool()
    if cleaned:
        log.info("warm_pool_drained", cleaned=cleaned)
