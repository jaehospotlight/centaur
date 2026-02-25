from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import structlog

from shared.sandbox.config import SandboxConfig

log = structlog.get_logger()

DOCKERFILE_TEMPLATE = textwrap.dedent("""\
    FROM ubuntu:24.04 AS base

    # System deps
    RUN apt-get update && apt-get install -y \\
        git curl wget build-essential pkg-config \\
        libssl-dev python3 python3-pip python3-venv \\
        && rm -rf /var/lib/apt/lists/*

    # Install uv
    RUN curl -LsSf https://astral.sh/uv/install.sh | sh
    ENV PATH="/root/.local/bin:${{PATH}}"

    # Install GitHub CLI
    RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \\
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \\
        && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \\
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \\
        && apt-get update && apt-get install -y gh \\
        && rm -rf /var/lib/apt/lists/*

    # Install Node.js (for TS repos)
    RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \\
        && apt-get install -y nodejs \\
        && rm -rf /var/lib/apt/lists/*

    # Install Rust (for Rust repos)
    RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    ENV PATH="/root/.cargo/bin:${{PATH}}"

    # Repos directory
    RUN mkdir -p /repos

    # Copy pre-cloned repos (populated by repo_sync)
    COPY repos/ /repos/

    # API client config
    ENV AI_V2_API_URL="{api_url}"

    # Working directory
    WORKDIR /repos

    # Entrypoint
    COPY entrypoint.sh /entrypoint.sh
    RUN chmod +x /entrypoint.sh
    ENTRYPOINT ["/entrypoint.sh"]
    CMD ["bash"]
""")


def _generate_dockerfile(config: SandboxConfig) -> str:
    """Generate a Dockerfile from the template with config values."""
    return DOCKERFILE_TEMPLATE.format(api_url=config.api_base_url)


def build_sandbox_image(
    config: SandboxConfig,
    tag: str | None = None,
    repos_dir: str = "/repos",
    context_dir: str | None = None,
) -> bool:
    """Build the Docker sandbox image.

    Args:
        config: Sandbox configuration.
        tag: Image tag. Defaults to "latest".
        repos_dir: Directory containing cloned repos to copy into the image.
        context_dir: Docker build context directory. Defaults to the sandbox package dir.

    Returns:
        True if build succeeded, False otherwise.
    """
    tag = tag or "latest"
    image_name = config.sandbox_image_name

    if context_dir:
        build_ctx = Path(context_dir)
    else:
        build_ctx = Path(__file__).parent.parent.parent
    build_ctx.mkdir(parents=True, exist_ok=True)

    # Write generated Dockerfile
    dockerfile_path = build_ctx / "Dockerfile.generated"
    dockerfile_content = _generate_dockerfile(config)
    dockerfile_path.write_text(dockerfile_content)
    log.info("generated_dockerfile", path=str(dockerfile_path))

    # Ensure repos dir exists in build context
    repos_in_ctx = build_ctx / "repos"
    if not repos_in_ctx.exists():
        # Symlink the repos dir into the build context
        repos_source = Path(repos_dir)
        if repos_source.exists():
            repos_in_ctx.symlink_to(repos_source)
            log.info("linked_repos", source=str(repos_source), target=str(repos_in_ctx))
        else:
            repos_in_ctx.mkdir(parents=True, exist_ok=True)
            log.warning("empty_repos_dir", path=str(repos_in_ctx))

    # Ensure entrypoint.sh exists in build context
    entrypoint_src = Path(__file__).parent.parent.parent / "entrypoint.sh"
    entrypoint_dst = build_ctx / "entrypoint.sh"
    if entrypoint_src.exists() and not entrypoint_dst.exists():
        entrypoint_dst.write_text(entrypoint_src.read_text())

    # Build the image
    full_tag = f"{image_name}:{tag}"
    latest_tag = f"{image_name}:latest"
    cmd = [
        "docker",
        "build",
        "-f",
        str(dockerfile_path),
        "-t",
        full_tag,
        "-t",
        latest_tag,
        str(build_ctx),
    ]

    log.info("building_image", image=full_tag, context=str(build_ctx))
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        log.info(
            "build_complete", image=full_tag, stdout=result.stdout[-500:] if result.stdout else ""
        )
        return True
    except subprocess.CalledProcessError as exc:
        log.error(
            "build_failed",
            image=full_tag,
            returncode=exc.returncode,
            stderr=exc.stderr[-1000:] if exc.stderr else "",
        )
        return False
    finally:
        # Clean up generated dockerfile
        if dockerfile_path.exists():
            dockerfile_path.unlink()
