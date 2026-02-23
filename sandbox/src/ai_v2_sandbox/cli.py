from __future__ import annotations

import asyncio
import subprocess
import sys

import click
import structlog

from ai_v2_sandbox.config import SandboxConfig
from ai_v2_sandbox.docker_builder import build_sandbox_image
from ai_v2_sandbox.repo_sync import sync_loop, sync_repos

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.get_logger()


@click.group()
@click.option(
    "--repos-dir",
    default="/repos",
    envvar="SANDBOX_REPOS_DIR",
    help="Directory to clone repos into.",
)
@click.option(
    "--api-url",
    default="http://localhost:8000",
    envvar="SANDBOX_API_BASE_URL",
    help="API base URL for sandbox containers.",
)
@click.pass_context
def cli(ctx: click.Context, repos_dir: str, api_url: str) -> None:
    """Tempo AI Sandbox — build Docker images preloaded with all Tempo repos."""
    ctx.ensure_object(dict)
    ctx.obj["repos_dir"] = repos_dir
    config = SandboxConfig(api_base_url=api_url)
    ctx.obj["config"] = config


@cli.command("sync-repos")
@click.pass_context
def sync_repos_cmd(ctx: click.Context) -> None:
    """Clone or update all configured repos to the local directory."""
    config: SandboxConfig = ctx.obj["config"]
    repos_dir: str = ctx.obj["repos_dir"]

    result = asyncio.run(sync_repos(config, target_dir=repos_dir))
    click.echo(f"Synced: {result.synced}, Failed: {result.failed}")
    if result.errors:
        click.echo("Errors:")
        for err in result.errors:
            click.echo(f"  - {err}")
        sys.exit(1)


@cli.command("build")
@click.option("--tag", default=None, help="Image tag (default: latest).")
@click.pass_context
def build_cmd(ctx: click.Context, tag: str | None) -> None:
    """Build Docker image with current repos."""
    config: SandboxConfig = ctx.obj["config"]
    repos_dir: str = ctx.obj["repos_dir"]

    success = build_sandbox_image(config, tag=tag, repos_dir=repos_dir)
    if success:
        image = f"{config.sandbox_image_name}:{tag or 'latest'}"
        click.echo(f"Built image: {image}")
    else:
        click.echo("Build failed. Check logs for details.", err=True)
        sys.exit(1)


@cli.command("update")
@click.option("--tag", default=None, help="Image tag (default: latest).")
@click.pass_context
def update_cmd(ctx: click.Context, tag: str | None) -> None:
    """Sync repos and rebuild the Docker image."""
    config: SandboxConfig = ctx.obj["config"]
    repos_dir: str = ctx.obj["repos_dir"]

    click.echo("Step 1/2: Syncing repos...")
    result = asyncio.run(sync_repos(config, target_dir=repos_dir))
    click.echo(f"  Synced: {result.synced}, Failed: {result.failed}")
    if result.errors:
        click.echo("  Errors during sync:")
        for err in result.errors:
            click.echo(f"    - {err}")

    click.echo("Step 2/2: Building image...")
    success = build_sandbox_image(config, tag=tag, repos_dir=repos_dir)
    if success:
        image = f"{config.sandbox_image_name}:{tag or 'latest'}"
        click.echo(f"Done. Image: {image}")
    else:
        click.echo("Build failed.", err=True)
        sys.exit(1)


@cli.command("run")
@click.option("--tag", default="latest", help="Image tag to run.")
@click.option(
    "--sync-on-start/--no-sync-on-start",
    default=False,
    help="Sync repos when container starts.",
)
@click.pass_context
def run_cmd(ctx: click.Context, tag: str, sync_on_start: bool) -> None:
    """Run sandbox container interactively."""
    config: SandboxConfig = ctx.obj["config"]
    image = f"{config.sandbox_image_name}:{tag}"

    cmd = [
        "docker", "run",
        "--rm", "-it",
        "-e", f"AI_V2_API_URL={config.api_base_url}",
    ]
    if sync_on_start:
        cmd.extend(["-e", "SYNC_ON_START=true"])

    cmd.append(image)

    click.echo(f"Starting sandbox: {image}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        click.echo(f"Container exited with code {exc.returncode}", err=True)
        sys.exit(exc.returncode)
    except FileNotFoundError:
        click.echo("Error: docker not found. Is Docker installed?", err=True)
        sys.exit(1)


@cli.command("cron")
@click.pass_context
def cron_cmd(ctx: click.Context) -> None:
    """Run continuous sync loop (for cron/systemd)."""
    config: SandboxConfig = ctx.obj["config"]
    repos_dir: str = ctx.obj["repos_dir"]

    click.echo(
        f"Starting sync loop (interval: {config.update_interval_hours}h, "
        f"dir: {repos_dir})"
    )
    try:
        asyncio.run(sync_loop(config, target_dir=repos_dir))
    except KeyboardInterrupt:
        click.echo("Sync loop stopped.")


if __name__ == "__main__":
    cli()
