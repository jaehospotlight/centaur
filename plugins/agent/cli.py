"""Agent sandbox CLI."""

import json

from dotenv import load_dotenv

load_dotenv()

import typer

app = typer.Typer(name="agent", help="Manage agent sandbox containers")


@app.command()
def spawn(
    thread_key: str = typer.Argument(..., help="Slack thread key (channel:thread_ts)"),
    harness: str = typer.Option("amp", "--harness", "-h", help="amp, claude-code, or codex"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Repo path in /repos/"),
):
    """Spawn a new sandbox container for a thread."""
    from .client import _client

    client = _client()
    result = client.spawn(thread_key, harness=harness, repo=repo)
    print(json.dumps(result, indent=2))


@app.command()
def execute(
    thread_key: str = typer.Argument(..., help="Slack thread key"),
    message: str = typer.Argument(..., help="Message to send to the agent"),
):
    """Execute a message in an existing sandbox."""
    from .client import _client

    client = _client()
    result = client.execute(thread_key, message)
    print(json.dumps(result, indent=2, default=str))


@app.command()
def status(
    thread_key: str | None = typer.Argument(None, help="Thread key (omit for all)"),
):
    """Show session status."""
    from .client import _client

    client = _client()
    result = client.status(thread_key)
    print(json.dumps(result, indent=2, default=str))


@app.command()
def stop(
    thread_key: str = typer.Argument(..., help="Thread key to stop"),
):
    """Stop and remove a sandbox."""
    from .client import _client

    client = _client()
    result = client.stop(thread_key)
    print(json.dumps(result, indent=2))


@app.command()
def interrupt(
    thread_key: str = typer.Argument(..., help="Thread key to interrupt"),
):
    """Interrupt the running command in a sandbox."""
    from .client import _client

    client = _client()
    result = client.interrupt(thread_key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
