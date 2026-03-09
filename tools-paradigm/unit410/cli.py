"""CLI for Unit 410 balances API."""

import json

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(name="unit410", help="Unit 410 CLI for wallet balances across networks")
console = Console()


def format_number(value: float, decimals: int = 4) -> str:
    """Format numbers with appropriate precision."""
    if abs(value) >= 1e6:
        return f"{value / 1e6:.2f}M"
    elif abs(value) >= 1e3:
        return f"{value / 1e3:.2f}K"
    elif abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.{decimals}f}"


@app.command()
def balances(
    network: str = typer.Option(
        None, "--network", "-n", help="Filter by network (ethereum, hyperliquid)"
    ),
    account: str = typer.Option(None, "--account", "-a", help="Filter by account (flp, onelp)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get all wallet balances."""
    from .client import Unit410Client

    client = Unit410Client()
    data = client.get_balances()

    if network:
        data = [w for w in data if w.get("network", "").lower() == network.lower()]
    if account:
        data = [w for w in data if w.get("account", "").lower() == account.lower()]

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not data:
        console.print("[yellow]No wallets found.[/]")
        raise typer.Exit()

    table = Table(title=f"Wallets ({len(data)})")
    table.add_column("Account", style="cyan", max_width=12)
    table.add_column("Network", style="green", max_width=15)
    table.add_column("Strategy", style="yellow", max_width=12)
    table.add_column("Address", style="dim", max_width=20)
    table.add_column("Balances", style="white")

    for wallet in data:
        account_name = wallet.get("account", "")
        network_name = wallet.get("network", "")
        strategy = wallet.get("strategy", "")
        address = (
            wallet.get("address", "")[:20] + "..."
            if len(wallet.get("address", "")) > 20
            else wallet.get("address", "")
        )

        balances_list = wallet.get("balances", [])
        balance_strs = []
        for b in balances_list:
            amt = b.get("amount", 0)
            denom = b.get("denom", "")
            kind = b.get("kind", "")
            if amt > 0:
                kind_suffix = f" ({kind})" if kind and kind != "available" else ""
                balance_strs.append(f"{format_number(amt)} {denom}{kind_suffix}")

        balance_display = ", ".join(balance_strs[:3]) if balance_strs else "[dim]empty[/dim]"
        if len(balance_strs) > 3:
            balance_display += f" (+{len(balance_strs) - 3} more)"

        table.add_row(account_name, network_name, strategy, address, balance_display)

    console.print(table)


@app.command()
def wallets(
    network: str = typer.Option(None, "--network", "-n", help="Filter by network"),
    account: str = typer.Option(None, "--account", "-a", help="Filter by account"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Alias for balances command."""
    from .client import Unit410Client

    client = Unit410Client()
    data = client.get_balances()

    if network:
        data = [w for w in data if w.get("network", "").lower() == network.lower()]
    if account:
        data = [w for w in data if w.get("account", "").lower() == account.lower()]

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not data:
        console.print("[yellow]No wallets found.[/]")
        raise typer.Exit()

    for wallet in data:
        console.print(
            f"\n[bold cyan]{wallet.get('account', '')}[/] / [green]{wallet.get('network', '')}[/]"
        )
        console.print(f"  [dim]Strategy:[/] {wallet.get('strategy', '')}")
        console.print(f"  [dim]Address:[/] {wallet.get('address', '')}")

        balances_list = wallet.get("balances", [])
        if balances_list:
            console.print("  [dim]Balances:[/]")
            for b in balances_list:
                amt = b.get("amount", 0)
                if amt > 0:
                    denom = b.get("denom", "")
                    kind = b.get("kind", "available")
                    console.print(f"    {format_number(amt)} {denom} [dim]({kind})[/]")


@app.command()
def summary(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show summary of balances by account and network."""
    from .client import Unit410Client

    client = Unit410Client()
    data = client.get_balances()

    if json_output:
        print(json.dumps(data, indent=2))
        return

    # Group by account
    by_account: dict[str, list] = {}
    for wallet in data:
        acc = wallet.get("account", "unknown")
        by_account.setdefault(acc, []).append(wallet)

    for account_name, wallets in sorted(by_account.items()):
        console.print(f"\n[bold cyan]{account_name}[/]")

        # Aggregate balances by denom
        totals: dict[str, float] = {}
        networks = set()
        for wallet in wallets:
            networks.add(wallet.get("network", ""))
            for b in wallet.get("balances", []):
                denom = b.get("denom", "")
                amt = b.get("amount", 0)
                totals[denom] = totals.get(denom, 0) + amt

        console.print(f"  [dim]Networks:[/] {', '.join(sorted(networks))}")
        console.print(f"  [dim]Wallets:[/] {len(wallets)}")
        if totals:
            console.print("  [dim]Total Balances:[/]")
            for denom, amt in sorted(totals.items(), key=lambda x: -x[1]):
                if amt > 0:
                    console.print(f"    {format_number(amt)} {denom}")


if __name__ == "__main__":
    app()
