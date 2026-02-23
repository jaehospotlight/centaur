from __future__ import annotations

import click
import uvicorn


@click.group()
def cli() -> None:
    """AI v2 API server."""


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool) -> None:
    """Run the API server."""
    uvicorn.run(
        "ai_v2_api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    cli()
