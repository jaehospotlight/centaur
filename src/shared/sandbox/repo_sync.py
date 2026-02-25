from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from shared.sandbox.config import RepoSpec, SandboxConfig

log = structlog.get_logger()


@dataclass
class SyncResult:
    """Result of a repository sync operation."""

    synced: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


async def _run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a subprocess command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


async def _sync_one_repo(
    spec: RepoSpec,
    target_dir: Path,
    token: str | None,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool, str | None]:
    """Clone or update a single repo. Returns (repo_name, success, error_msg)."""
    async with semaphore:
        repo_dir = target_dir / spec.org / spec.name
        clone_url = spec.get_clone_url(token if token else None)

        if repo_dir.exists() and (repo_dir / ".git").exists():
            log.info("updating_repo", repo=spec.full_name)
            rc, _out, err = await _run_cmd(["git", "fetch", "origin"], cwd=repo_dir)
            if rc != 0:
                return spec.full_name, False, f"fetch failed: {err.strip()}"

            rc, _out, err = await _run_cmd(["git", "reset", "--hard", "origin/HEAD"], cwd=repo_dir)
            if rc != 0:
                return spec.full_name, False, f"reset failed: {err.strip()}"

            log.info("updated_repo", repo=spec.full_name)
            return spec.full_name, True, None
        else:
            log.info("cloning_repo", repo=spec.full_name, shallow=spec.shallow)
            repo_dir.parent.mkdir(parents=True, exist_ok=True)

            cmd = ["git", "clone"]
            if spec.shallow:
                cmd.extend(["--depth", "1"])
            if spec.branch != "main":
                cmd.extend(["--branch", spec.branch])
            cmd.extend([clone_url, str(repo_dir)])

            rc, _out, err = await _run_cmd(cmd)
            if rc != 0:
                return spec.full_name, False, f"clone failed: {err.strip()}"

            log.info("cloned_repo", repo=spec.full_name)
            return spec.full_name, True, None


async def sync_repos(config: SandboxConfig, target_dir: str = "/repos") -> SyncResult:
    """Clone or update all configured repos.

    Uses asyncio.subprocess for parallel cloning with max 5 concurrent operations.
    """
    result = SyncResult()
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    specs = config.get_repo_specs()
    token = config.github_token if config.github_token else None
    semaphore = asyncio.Semaphore(5)

    tasks = [_sync_one_repo(spec, target_path, token, semaphore) for spec in specs]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in outcomes:
        if isinstance(outcome, Exception):
            result.failed += 1
            result.errors.append(str(outcome))
        else:
            repo_name, success, error_msg = outcome
            if success:
                result.synced += 1
            else:
                result.failed += 1
                result.errors.append(f"{repo_name}: {error_msg}")

    log.info(
        "sync_complete",
        synced=result.synced,
        failed=result.failed,
        errors=result.errors,
    )
    return result


async def sync_loop(config: SandboxConfig, target_dir: str = "/repos") -> None:
    """Run sync_repos on a recurring interval. Runs forever."""
    interval_seconds = config.update_interval_hours * 3600
    log.info(
        "sync_loop_started",
        interval_hours=config.update_interval_hours,
        target_dir=target_dir,
    )

    while True:
        try:
            result = await sync_repos(config, target_dir)
            log.info(
                "sync_loop_iteration",
                synced=result.synced,
                failed=result.failed,
            )
        except Exception:
            log.exception("sync_loop_error")

        await asyncio.sleep(interval_seconds)
