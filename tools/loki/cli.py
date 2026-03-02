"""CLI for Loki log queries."""

import json

import typer
from dotenv import load_dotenv
from rich.console import Console
from shared.cli_tables import Table

load_dotenv()

app = typer.Typer(name="loki", help="Loki CLI for LogQL queries and log exploration")
console = Console()


def get_client():
    from .client import LokiClient

    return LokiClient()


@app.command("query")
def query_logs(
    query: str = typer.Argument(..., help='LogQL expression (e.g. \'{job="api"} |= "error"\')'),
    start: str = typer.Option(None, "--start", "-s", help="Range start (RFC3339 or epoch)"),
    end: str = typer.Option(None, "--end", "-e", help="Range end"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max log lines"),
    direction: str = typer.Option("backward", "--direction", "-d", help="backward or forward"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run a LogQL query against Loki."""
    client = get_client()
    result = client.query(query=query, limit=limit, start=start, end=end, direction=direction)

    if json_output:
        print(json.dumps(result, indent=2))
        return

    data = result.get("data", {})
    streams = data.get("result", [])

    if not streams:
        console.print("[yellow]No results[/]")
        return

    for stream in streams:
        labels = stream.get("stream", {})
        label_str = ", ".join(f"{k}={v}" for k, v in labels.items())
        console.print(f"[cyan]--- {label_str} ---[/]")
        for ts, line in stream.get("values", []):
            console.print(f"  {line}")


@app.command("labels")
def list_labels(
    start: str = typer.Option(None, "--start", "-s", help="Start time filter"),
    end: str = typer.Option(None, "--end", "-e", help="End time filter"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all known label names."""
    client = get_client()
    result = client.labels(start=start, end=end)

    if json_output:
        print(json.dumps(result, indent=2))
        return

    for label in result:
        console.print(f"  {label}")


@app.command("label-values")
def label_values(
    label: str = typer.Argument(..., help="Label name (e.g. container_name, job)"),
    start: str = typer.Option(None, "--start", "-s", help="Start time filter"),
    end: str = typer.Option(None, "--end", "-e", help="End time filter"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get all values for a label."""
    client = get_client()
    result = client.label_values(label, start=start, end=end)

    if json_output:
        print(json.dumps(result, indent=2))
        return

    for value in result:
        console.print(f"  {value}")


@app.command("series")
def list_series(
    match: str = typer.Argument(..., help='Label matcher (e.g. \'{job="api"}\')'),
    start: str = typer.Option(None, "--start", "-s", help="Start time filter"),
    end: str = typer.Option(None, "--end", "-e", help="End time filter"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Find log series matching a selector."""
    client = get_client()
    result = client.series(match=match, start=start, end=end)

    if json_output:
        print(json.dumps(result, indent=2))
        return

    if not result:
        console.print("[yellow]No series found[/]")
        return

    table = Table(title="Series")
    if result:
        cols = sorted(result[0].keys())
        for col in cols:
            table.add_column(col, style="cyan")
        for s in result:
            table.add_row(*[str(s.get(c, "")) for c in cols])

    console.print(table)


@app.command()
def health():
    """Check Loki readiness."""
    client = get_client()
    if client.ready():
        console.print("[green]Loki is ready[/]")
    else:
        console.print("[red]Loki is not ready[/]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
