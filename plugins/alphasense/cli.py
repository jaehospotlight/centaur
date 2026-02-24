"""CLI for AlphaSense API."""

import json
from datetime import datetime
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="alphasense", help="AlphaSense CLI for market intelligence and document search"
)
console = Console()


class DatePreset(str, Enum):
    LAST_24_HOURS = "LAST_24_HOURS"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    LAST_90_DAYS = "LAST_90_DAYS"
    LAST_6_MONTHS = "LAST_6_MONTHS"
    LAST_12_MONTHS = "LAST_12_MONTHS"
    LAST_18_MONTHS = "LAST_18_MONTHS"
    LAST_2_YEARS = "LAST_2_YEARS"


class SortField(str, Enum):
    RELEVANCE = "RELEVANCE"
    DATE = "DATE"
    PAGES = "PAGES"
    SENTIMENT = "SENTIMENT"


class SortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


def get_client():
    from .client import AlphaSenseClient

    return AlphaSenseClient()


def format_timestamp(epoch_ms: float | None) -> str:
    """Format epoch timestamp (ms) to readable date."""
    if epoch_ms is None:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return "N/A"


def truncate(text: str | None, max_len: int = 60) -> str:
    """Truncate text to max length."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def print_markdown_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a markdown-formatted table."""
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        print("| " + " | ".join(str(cell) for cell in row) + " |")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (supports AND/OR/NOT)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results (1-100)"),
    date: DatePreset = typer.Option(DatePreset.LAST_30_DAYS, "--date", "-d", help="Date filter"),
    sort: SortField = typer.Option(SortField.DATE, "--sort", "-s", help="Sort field"),
    order: SortDirection = typer.Option(SortDirection.DESC, "--order", "-o", help="Sort order"),
    companies: str = typer.Option(
        None, "--companies", "-c", help="Company tickers (comma-separated)"
    ),
    types: str = typer.Option(None, "--types", "-t", help="Document type IDs (comma-separated)"),
    countries: str = typer.Option(None, "--countries", help="Country codes (comma-separated)"),
    cursor: str = typer.Option(None, "--cursor", help="Pagination cursor"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Search for documents across AlphaSense content."""
    client = get_client()

    company_list = [c.strip() for c in companies.split(",")] if companies else None
    type_list = [t.strip() for t in types.split(",")] if types else None
    country_list = [c.strip().upper() for c in countries.split(",")] if countries else None

    try:
        data = client.search(
            query=query,
            limit=limit,
            date_preset=date.value,
            sort_field=sort.value,
            sort_direction=order.value,
            cursor=cursor,
            companies=company_list,
            doc_types=type_list,
            countries=country_list,
        )
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    search_data = data.get("search", {})
    documents = search_data.get("documents", [])
    total_count = search_data.get("totalCount", 0)
    next_cursor = search_data.get("cursor")

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not documents:
        console.print(f"[yellow]No results for '{query}'[/]")
        raise typer.Exit()

    if markdown:
        rows = []
        for doc in documents:
            companies_str = ", ".join(
                c.get("primaryTickerCode") or c.get("name", "")
                for c in doc.get("companies", [])[:3]
            )
            type_str = doc.get("type", {}).get("display") or "N/A"
            rows.append(
                [
                    doc.get("id", "")[:12],
                    truncate(doc.get("title", ""), 50),
                    format_timestamp(doc.get("releasedAt")),
                    type_str,
                    companies_str or "N/A",
                ]
            )
        print(f"**Total: {total_count} results**\n")
        print_markdown_table(["ID", "Title", "Date", "Type", "Companies"], rows)
        if next_cursor:
            print(f"\n*Next cursor: `{next_cursor}`*")
        return

    console.print(f"\n[bold]Found {total_count} documents[/] (showing {len(documents)})\n")

    table = Table(title=f"Search: '{query}'")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Title", style="cyan", max_width=50)
    table.add_column("Date", style="yellow")
    table.add_column("Type", style="green", max_width=20)
    table.add_column("Companies", style="blue", max_width=25)

    for doc in documents:
        companies_str = ", ".join(
            c.get("primaryTickerCode") or c.get("name", "") for c in doc.get("companies", [])[:3]
        )
        type_str = doc.get("type", {}).get("display") or "N/A"
        table.add_row(
            doc.get("id", "")[:12],
            truncate(doc.get("title", ""), 50),
            format_timestamp(doc.get("releasedAt")),
            truncate(type_str, 20),
            companies_str or "N/A",
        )

    console.print(table)

    if next_cursor:
        console.print(f"\n[dim]Next cursor: {next_cursor}[/]")


@app.command()
def document(
    doc_id: str = typer.Argument(..., help="Document ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown"),
):
    """Get document details by ID."""
    client = get_client()

    try:
        data = client.get_document(doc_id)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    doc = data.get("searchByDocId")
    if not doc:
        console.print(f"[yellow]Document not found: {doc_id}[/]")
        raise typer.Exit(1)

    if json_output:
        print(json.dumps(data, indent=2))
        return

    type_str = doc.get("type", {}).get("display") or "N/A"
    companies_list = doc.get("companies", [])
    companies_str = ", ".join(
        f"{c.get('primaryTickerCode') or ''} ({c.get('name', '')})" for c in companies_list[:5]
    )
    summary = doc.get("summary", [])
    summary_str = " ".join(summary) if summary else "N/A"
    sentiment = doc.get("sentiment", {})
    source_url = doc.get("source", {}).get("originalUrl", "N/A")

    if markdown:
        print(f"# {doc.get('title', 'Untitled')}\n")
        print(f"**ID:** {doc.get('id', 'N/A')}")
        print(f"**Date:** {format_timestamp(doc.get('releasedAt'))}")
        print(f"**Type:** {type_str}")
        print(f"**Pages:** {doc.get('pageCount', 'N/A')}")
        print(f"**Source:** {source_url}")
        print(f"**Companies:** {companies_str or 'N/A'}")
        print(f"**Countries:** {', '.join(doc.get('countryCodes', [])) or 'N/A'}")
        if sentiment:
            print(
                f"**Sentiment:** {sentiment.get('score', 'N/A')} (change: {sentiment.get('changePercentage', 'N/A')}%)"
            )
        print(f"\n**Summary:** {truncate(summary_str, 300)}")
        return

    console.print(f"\n[bold cyan]{doc.get('title', 'Untitled')}[/]\n")
    console.print(f"[dim]ID:[/] {doc.get('id', 'N/A')}")
    console.print(f"[dim]Date:[/] {format_timestamp(doc.get('releasedAt'))}")
    console.print(f"[dim]Type:[/] {type_str}")
    console.print(f"[dim]Pages:[/] {doc.get('pageCount', 'N/A')}")
    console.print(f"[dim]Source:[/] {source_url}")
    console.print(f"[dim]Companies:[/] {companies_str or 'N/A'}")
    console.print(f"[dim]Countries:[/] {', '.join(doc.get('countryCodes', [])) or 'N/A'}")
    if sentiment:
        console.print(
            f"[dim]Sentiment:[/] {sentiment.get('score', 'N/A')} (change: {sentiment.get('changePercentage', 'N/A')}%)"
        )
    console.print(f"\n[bold]Summary:[/] {truncate(summary_str, 300)}")


@app.command()
def companies(
    tickers: str = typer.Argument(..., help="Tickers to lookup (comma-separated)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Look up companies by ticker."""
    client = get_client()

    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    inputs = [{"tickerCode": t} for t in ticker_list]

    try:
        data = client.lookup_companies(inputs)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    companies_data = data.get("companies", [])

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if markdown:
        rows = []
        for c in companies_data:
            if c:
                country = c.get("country", {}) or {}
                rows.append(
                    [
                        c.get("id", "N/A"),
                        c.get("primaryTickerCode") or "N/A",
                        c.get("name", "N/A"),
                        country.get("code") or "N/A",
                        c.get("type", "N/A"),
                    ]
                )
        print_markdown_table(["ID", "Ticker", "Name", "Country", "Type"], rows)
        return

    table = Table(title="Company Lookup")
    table.add_column("ID", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Name", style="white", max_width=40)
    table.add_column("Country", style="yellow")
    table.add_column("Type", style="green")

    for c in companies_data:
        if c:
            country = c.get("country", {}) or {}
            table.add_row(
                c.get("id", "N/A"),
                c.get("primaryTickerCode") or "N/A",
                c.get("name", "N/A"),
                country.get("code") or "N/A",
                c.get("type", "N/A"),
            )

    console.print(table)


@app.command()
def watchlists(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """List user's watchlists."""
    client = get_client()

    try:
        data = client.get_watchlists()
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    watchlists_data = data.get("myWatchlists", [])

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not watchlists_data:
        console.print("[yellow]No watchlists found[/]")
        raise typer.Exit()

    if markdown:
        rows = []
        for w in watchlists_data:
            rows.append(
                [
                    w.get("id", "N/A"),
                    w.get("name", "N/A"),
                    str(w.get("companiesCount", 0)),
                    w.get("type", "N/A"),
                ]
            )
        print_markdown_table(["ID", "Name", "Companies", "Type"], rows)
        return

    table = Table(title="Watchlists")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Companies", style="yellow", justify="right")
    table.add_column("Type", style="green")

    for w in watchlists_data:
        table.add_row(
            w.get("id", "N/A"),
            w.get("name", "N/A"),
            str(w.get("companiesCount", 0)),
            w.get("type", "N/A"),
        )

    console.print(table)


@app.command()
def watchlist(
    watchlist_id: str = typer.Argument(..., help="Watchlist ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Get companies in a watchlist."""
    client = get_client()

    try:
        data = client.get_watchlist_companies(watchlist_id)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    watchlist_data = data.get("myWatchlist")
    if not watchlist_data:
        console.print(f"[yellow]Watchlist not found: {watchlist_id}[/]")
        raise typer.Exit(1)

    if json_output:
        print(json.dumps(data, indent=2))
        return

    companies_data = watchlist_data.get("companies", [])

    if markdown:
        print(f"# {watchlist_data.get('name', 'Watchlist')}\n")
        rows = []
        for c in companies_data:
            country = c.get("country", {}) or {}
            rows.append(
                [
                    c.get("id", "N/A"),
                    c.get("primaryTickerCode") or "N/A",
                    c.get("name", "N/A"),
                    country.get("code") or "N/A",
                ]
            )
        print_markdown_table(["ID", "Ticker", "Name", "Country"], rows)
        return

    console.print(f"\n[bold]{watchlist_data.get('name', 'Watchlist')}[/]\n")

    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Name", style="white", max_width=40)
    table.add_column("Country", style="yellow")

    for c in companies_data:
        country = c.get("country", {}) or {}
        table.add_row(
            c.get("id", "N/A"),
            c.get("primaryTickerCode") or "N/A",
            c.get("name", "N/A"),
            country.get("code") or "N/A",
        )

    console.print(table)


@app.command()
def saved(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """List saved searches."""
    client = get_client()

    try:
        data = client.get_saved_searches()
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    searches = data.get("savedSearches", [])

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not searches:
        console.print("[yellow]No saved searches found[/]")
        raise typer.Exit()

    if markdown:
        rows = [[s.get("id", "N/A"), s.get("name", "N/A")] for s in searches]
        print_markdown_table(["ID", "Name"], rows)
        return

    table = Table(title="Saved Searches")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan", max_width=50)

    for s in searches:
        table.add_row(s.get("id", "N/A"), s.get("name", "N/A"))

    console.print(table)


@app.command()
def run_saved(
    search_id: str = typer.Argument(..., help="Saved search ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    cursor: str = typer.Option(None, "--cursor", help="Pagination cursor"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as markdown table"),
):
    """Execute a saved search."""
    client = get_client()

    try:
        data = client.search_by_saved_id(search_id, limit=limit, cursor=cursor)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    search_data = data.get("searchById", {}).get("search", {})
    documents = search_data.get("documents", [])
    total_count = search_data.get("totalCount", 0)
    next_cursor = search_data.get("cursor")

    if json_output:
        print(json.dumps(data, indent=2))
        return

    if not documents:
        console.print("[yellow]No results[/]")
        raise typer.Exit()

    if markdown:
        rows = []
        for doc in documents:
            companies_str = ", ".join(
                c.get("primaryTickerCode") or c.get("name", "")
                for c in doc.get("companies", [])[:3]
            )
            type_str = doc.get("type", {}).get("display") or "N/A"
            rows.append(
                [
                    doc.get("id", "")[:12],
                    truncate(doc.get("title", ""), 50),
                    format_timestamp(doc.get("releasedAt")),
                    type_str,
                    companies_str or "N/A",
                ]
            )
        print(f"**Total: {total_count} results**\n")
        print_markdown_table(["ID", "Title", "Date", "Type", "Companies"], rows)
        if next_cursor:
            print(f"\n*Next cursor: `{next_cursor}`*")
        return

    console.print(f"\n[bold]Found {total_count} documents[/] (showing {len(documents)})\n")

    table = Table()
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Title", style="cyan", max_width=50)
    table.add_column("Date", style="yellow")
    table.add_column("Type", style="green", max_width=20)
    table.add_column("Companies", style="blue", max_width=25)

    for doc in documents:
        companies_str = ", ".join(
            c.get("primaryTickerCode") or c.get("name", "") for c in doc.get("companies", [])[:3]
        )
        type_str = doc.get("type", {}).get("display") or "N/A"
        table.add_row(
            doc.get("id", "")[:12],
            truncate(doc.get("title", ""), 50),
            format_timestamp(doc.get("releasedAt")),
            truncate(type_str, 20),
            companies_str or "N/A",
        )

    console.print(table)

    if next_cursor:
        console.print(f"\n[dim]Next cursor: {next_cursor}[/]")


@app.command()
def whoami(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show current user info."""
    client = get_client()

    try:
        data = client.get_user()
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    user = data.get("user", {})

    if json_output:
        print(json.dumps(data, indent=2))
        return

    console.print(f"\n[bold]User ID:[/] {user.get('id', 'N/A')}")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask AlphaSense"),
    timeout: int = typer.Option(150, "--timeout", "-t", help="Max seconds to wait for response"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Ask a question using AlphaSense Generative Search."""
    client = get_client()

    max_attempts = max(1, timeout // 5)

    try:
        console.print("[dim]Searching AlphaSense...[/]", end="")
        data = client.gen_search(prompt=question, max_attempts=max_attempts, poll_interval=5.0)
        console.print("\r[green]✓ Search complete[/]      ")
    except RuntimeError as e:
        console.print(f"\r[red]Error: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        print(json.dumps(data, indent=2))
        return

    markdown_content = data.get("markdown", "")
    conversation_id = data.get("id", "")

    if not markdown_content:
        console.print("[yellow]No results found[/]")
        raise typer.Exit()

    print(markdown_content)

    if conversation_id:
        console.print(
            f"\n[dim]View in AlphaSense: https://research.alpha-sense.com/gensearch/{conversation_id}[/]"
        )


@app.command()
def raw(
    query: str = typer.Argument(..., help="GraphQL query string"),
    variables: str = typer.Option(None, "--vars", "-v", help="Variables as JSON string"),
):
    """Execute a raw GraphQL query."""
    client = get_client()

    vars_dict = None
    if variables:
        try:
            vars_dict = json.loads(variables)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON variables: {e}[/]")
            raise typer.Exit(1)

    try:
        data = client._graphql_request(query, vars_dict)
        print(json.dumps(data, indent=2))
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
