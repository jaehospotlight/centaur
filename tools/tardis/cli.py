"""CLI for Tardis.dev API."""

import asyncio
import json

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(name="tardis", help="Tardis CLI for CEX market data replay and analytics")
console = Console()


def get_client():
    from .client import TardisClient

    return TardisClient()


def print_markdown_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a markdown-formatted table."""
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        print("| " + " | ".join(str(cell) for cell in row) + " |")


@app.command()
def exchanges(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """List available exchanges."""
    client = get_client()
    data = client.list_exchanges()

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if markdown:
        rows = []
        for ex in data:
            rows.append(
                [
                    ex.get("id", ""),
                    ex.get("name", ""),
                    ex.get("availableSince", "")[:10] if ex.get("availableSince") else "",
                ]
            )
        print_markdown_table(["ID", "Name", "Available Since"], rows)
        return

    table = Table(title="Available Exchanges")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Available Since", style="dim")

    for ex in data:
        since = ex.get("availableSince", "")[:10] if ex.get("availableSince") else ""
        table.add_row(ex.get("id", ""), ex.get("name", ""), since)

    console.print(table)


@app.command()
def instruments(
    exchange: str = typer.Argument(..., help="Exchange ID (e.g., binance, bitmex)"),
    active: bool = typer.Option(True, "--active/--all", help="Show only active instruments"),
    base: str = typer.Option(None, "--base", "-b", help="Filter by base currency (e.g., BTC)"),
    quote: str = typer.Option(None, "--quote", "-q", help="Filter by quote currency (e.g., USDT)"),
    type_filter: str = typer.Option(
        None, "--type", "-t", help="Filter by type (spot, perpetual, future, option)"
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Get instrument metadata for an exchange."""
    client = get_client()

    filter_obj = {}
    if active:
        filter_obj["active"] = True
    if base:
        filter_obj["baseCurrency"] = base.upper()
    if quote:
        filter_obj["quoteCurrency"] = quote.upper()
    if type_filter:
        filter_obj["type"] = type_filter

    try:
        data = client.get_instruments(exchange, filter_obj if filter_obj else None)
    except RuntimeError as e:
        if "401" in str(e) or "403" in str(e):
            console.print(
                "[yellow]Note: Instruments API requires a pro subscription. "
                "Falling back to exchange symbols.[/]"
            )
            ex_data = client.get_exchange(exchange)
            symbols = ex_data.get("availableSymbols", [])
            if json_output:
                print(json.dumps(symbols[:limit], indent=2))
                return
            table = Table(title=f"Symbols for {exchange}")
            table.add_column("Symbol", style="cyan")
            table.add_column("Available Since", style="dim")
            table.add_column("Available To", style="dim")
            for sym in symbols[:limit]:
                if isinstance(sym, dict):
                    table.add_row(
                        sym.get("id", ""),
                        sym.get("availableSince", "")[:10] if sym.get("availableSince") else "",
                        sym.get("availableTo", "")[:10] if sym.get("availableTo") else "active",
                    )
                else:
                    table.add_row(str(sym), "", "")
            console.print(table)
            return
        raise

    data = data[:limit]

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if markdown:
        rows = []
        for inst in data:
            rows.append(
                [
                    inst.get("id", ""),
                    inst.get("baseCurrency", ""),
                    inst.get("quoteCurrency", ""),
                    inst.get("type", ""),
                    "Yes" if inst.get("active") else "No",
                ]
            )
        print_markdown_table(["Symbol", "Base", "Quote", "Type", "Active"], rows)
        return

    table = Table(title=f"Instruments for {exchange}")
    table.add_column("Symbol", style="cyan")
    table.add_column("Base", style="green")
    table.add_column("Quote", style="yellow")
    table.add_column("Type", style="dim")
    table.add_column("Active", style="dim")

    for inst in data:
        table.add_row(
            inst.get("id", ""),
            inst.get("baseCurrency", ""),
            inst.get("quoteCurrency", ""),
            inst.get("type", ""),
            "Yes" if inst.get("active") else "No",
        )

    console.print(table)


@app.command()
def replay(
    exchange: str = typer.Argument(..., help="Exchange ID (e.g., binance, bitmex)"),
    symbol: str = typer.Argument(..., help="Symbol (e.g., BTCUSDT, XBTUSD)"),
    from_date: str = typer.Option(..., "--from", "-f", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option(..., "--to", "-t", help="End date (YYYY-MM-DD)"),
    data_type: str = typer.Option("trades", "--data-type", "-d", help="Data type: trades or book"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max messages to display"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Replay historical trades or orderbook data."""
    from tardis_dev import TardisClient, Channel

    import os

    api_key = os.getenv("TARDIS_API_KEY", "")

    channel_map = {
        "trades": "trade",
        "trade": "trade",
        "book": "book",
        "orderbook": "book",
    }

    channel_name = channel_map.get(data_type.lower(), data_type)

    async def run_replay():
        client = TardisClient(api_key=api_key)
        messages = []

        try:
            async for local_timestamp, message in client.replay(
                exchange=exchange,
                from_date=from_date,
                to_date=to_date,
                filters=[Channel(name=channel_name, symbols=[symbol])],
            ):
                messages.append({"timestamp": str(local_timestamp), "message": message})
                if len(messages) >= limit:
                    break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            raise typer.Exit(1)

        return messages

    messages = asyncio.run(run_replay())

    if not messages:
        console.print("[yellow]No data found for the specified parameters.[/]")
        return

    if json_output:
        print(json.dumps(messages, indent=2, default=str))
        return

    console.print(f"\n[bold]Replay: {exchange} {symbol}[/] ({data_type})")
    console.print(f"[dim]From: {from_date} To: {to_date}[/]\n")

    for msg in messages[:20]:
        ts = msg["timestamp"]
        data = msg["message"]
        console.print(f"[dim]{ts}[/]")
        console.print(f"  {json.dumps(data, default=str)[:200]}")

    if len(messages) > 20:
        console.print(f"\n[dim]... and {len(messages) - 20} more messages[/]")


@app.command()
def funding(
    exchange: str = typer.Argument(..., help="Exchange ID (e.g., binance-futures, bitmex)"),
    symbol: str = typer.Argument(..., help="Symbol (e.g., BTCUSDT, XBTUSD)"),
    from_date: str = typer.Option(..., "--from", "-f", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option(..., "--to", "-t", help="End date (YYYY-MM-DD)"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max messages to display"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Get funding rates for a perpetual contract."""
    from tardis_dev import TardisClient, Channel

    import os

    api_key = os.getenv("TARDIS_API_KEY", "")

    async def run_replay():
        client = TardisClient(api_key=api_key)
        messages = []

        try:
            async for local_timestamp, message in client.replay(
                exchange=exchange,
                from_date=from_date,
                to_date=to_date,
                filters=[Channel(name="derivative_ticker", symbols=[symbol])],
            ):
                if "fundingRate" in message or "funding_rate" in message:
                    rate = message.get("fundingRate") or message.get("funding_rate")
                    messages.append(
                        {
                            "timestamp": str(local_timestamp),
                            "funding_rate": rate,
                            "message": message,
                        }
                    )
                    if len(messages) >= limit:
                        break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            raise typer.Exit(1)

        return messages

    messages = asyncio.run(run_replay())

    if not messages:
        console.print("[yellow]No funding rate data found.[/]")
        console.print("[dim]Tip: Try derivative exchanges like binance-futures, bitmex, bybit[/]")
        return

    if json_output:
        print(json.dumps(messages, indent=2, default=str))
        return

    if markdown:
        rows = []
        for msg in messages:
            ts = msg["timestamp"][:19] if len(msg["timestamp"]) > 19 else msg["timestamp"]
            rate = msg.get("funding_rate", "N/A")
            if isinstance(rate, (int, float)):
                rate = f"{float(rate) * 100:.6f}%"
            rows.append([ts, str(rate)])
        print_markdown_table(["Timestamp", "Funding Rate"], rows)
        return

    table = Table(title=f"Funding Rates: {exchange} {symbol}")
    table.add_column("Timestamp", style="dim")
    table.add_column("Funding Rate", style="cyan", justify="right")

    for msg in messages:
        ts = msg["timestamp"][:19] if len(msg["timestamp"]) > 19 else msg["timestamp"]
        rate = msg.get("funding_rate", "N/A")
        if isinstance(rate, (int, float)):
            rate = f"{float(rate) * 100:.6f}%"
        table.add_row(ts, str(rate))

    console.print(table)


@app.command()
def channels(
    exchange: str = typer.Argument(..., help="Exchange ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List available data channels for an exchange."""
    client = get_client()
    data = client.get_exchange(exchange)

    channels = data.get("availableChannels", [])

    if json_output:
        print(json.dumps(channels, indent=2))
        return

    console.print(f"\n[bold]Available channels for {exchange}:[/]\n")
    for ch in channels:
        console.print(f"  • {ch}")


if __name__ == "__main__":
    app()
