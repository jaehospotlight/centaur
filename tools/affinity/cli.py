"""CLI for Affinity CRM."""

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="affinity", help="Affinity CRM CLI for AI agents")
console = Console()


@app.command()
def whoami(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show info about current API token."""
    from .client import _client

    client = _client()
    info = client.whoami()

    if json_output:
        print(json.dumps(info, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    tenant = info.get("tenant", {})
    user = info.get("user", {})
    console.print(f"[bold]Tenant:[/] {tenant.get('name', 'N/A')}")
    console.print(f"[bold]User:[/] {user.get('first_name', '')} {user.get('last_name', '')}")
    console.print(f"[bold]Email:[/] {user.get('email', 'N/A')}")


@app.command()
def lists(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all lists."""
    from .client import _client

    client = _client()
    data = client.list_lists()

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    if not data:
        console.print("[yellow]No lists found.[/]")
        raise typer.Exit()

    table = Table(title=f"Lists ({len(data)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="cyan", max_width=30)
    table.add_column("Type", style="green", max_width=15)
    table.add_column("Public", style="yellow", max_width=8)

    # Type mapping: 0=person, 1=organization, 8=opportunity
    type_names = {0: "person", 1: "organization", 8: "opportunity"}
    for lst in data:
        list_id = str(lst.get("id", ""))
        name = lst.get("name", "")
        list_type = type_names.get(lst.get("type"), str(lst.get("type", "")))
        public = "yes" if lst.get("public", False) else ""
        table.add_row(list_id, name, list_type, public)

    console.print(table)


@app.command("list")
def get_list_cmd(
    list_id: int = typer.Argument(..., help="List ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get list details."""
    from .client import _client

    client = _client()
    data = client.get_list(list_id)

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    console.print(f"[bold]Name:[/] {data.get('name', 'N/A')}")
    console.print(f"[bold]ID:[/] {data.get('id', 'N/A')}")
    console.print(f"[bold]Type:[/] {data.get('type', 'N/A')}")
    console.print(f"[bold]Creator ID:[/] {data.get('creator_id', 'N/A')}")
    console.print(f"[bold]Public:[/] {data.get('public', False)}")

    fields = data.get("fields", [])
    if fields:
        console.print(f"\n[bold]Fields ({len(fields)}):[/]")
        for field in fields:
            console.print(f"  - {field.get('name', '')} ({field.get('value_type', '')})")


@app.command()
def entries(
    list_id: int = typer.Argument(..., help="List ID"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get entries in a list."""
    from .client import _client

    client = _client()
    data = client.get_list_entries(list_id, page_size=limit)
    entries_list = data.get("list_entries", [])

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    if not entries_list:
        console.print("[yellow]No entries found.[/]")
        raise typer.Exit()

    table = Table(title=f"List Entries ({len(entries_list)})")
    table.add_column("Entry ID", style="dim", max_width=12)
    table.add_column("Entity ID", style="cyan", max_width=12)
    table.add_column("Entity Type", style="green", max_width=15)
    table.add_column("Created At", style="white", max_width=20)

    for entry in entries_list:
        entry_id = str(entry.get("id", ""))
        entity_id = str(entry.get("entity_id", ""))
        entity = entry.get("entity", {})
        entity_type = entity.get("type", "") if entity else ""
        created_at = entry.get("created_at", "")[:10] if entry.get("created_at") else ""
        table.add_row(entry_id, entity_id, entity_type, created_at)

    console.print(table)

    if data.get("next_page_token"):
        console.print("\n[dim]More results available. Use --limit to increase.[/]")


@app.command()
def persons(
    term: str = typer.Option(None, "--term", "-t", help="Search term"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List/search persons."""
    from .client import _client

    client = _client()
    data = client.search_persons(term=term, page_size=limit)
    persons_list = data.get("persons", [])

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    if not persons_list:
        console.print("[yellow]No persons found.[/]")
        raise typer.Exit()

    table = Table(title=f"Persons ({len(persons_list)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="cyan", max_width=30)
    table.add_column("Email", style="white", max_width=35)

    for person in persons_list:
        person_id = str(person.get("id", ""))
        first = person.get("first_name", "") or ""
        last = person.get("last_name", "") or ""
        name = f"{first} {last}".strip()
        email = person.get("primary_email", "") or ""
        table.add_row(person_id, name, email)

    console.print(table)


@app.command()
def person(
    person_id: int = typer.Argument(..., help="Person ID"),
    interactions: bool = typer.Option(False, "--interactions", "-i", help="Include interactions"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get person details."""
    from .client import _client

    client = _client()
    data = client.get_person(person_id, with_interaction_dates=interactions)

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    first = data.get("first_name", "") or ""
    last = data.get("last_name", "") or ""
    console.print(f"[bold]Name:[/] {first} {last}")
    console.print(f"[bold]ID:[/] {data.get('id', 'N/A')}")
    console.print(f"[bold]Primary Email:[/] {data.get('primary_email', 'N/A')}")

    emails = data.get("emails", [])
    if emails:
        console.print(f"[bold]All Emails:[/] {', '.join(emails)}")

    org_ids = data.get("organization_ids", [])
    if org_ids:
        console.print(f"[bold]Organization IDs:[/] {', '.join(map(str, org_ids))}")

    if interactions:
        dates = data.get("interaction_dates", {})
        if dates:
            console.print("\n[bold]Interactions:[/]")
            for key, val in dates.items():
                if val:
                    console.print(f"  {key}: {val}")


@app.command()
def organizations(
    term: str = typer.Option(None, "--term", "-t", help="Search term"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List/search organizations."""
    from .client import _client

    client = _client()
    data = client.search_organizations(term=term, page_size=limit)
    orgs_list = data.get("organizations", [])

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    if not orgs_list:
        console.print("[yellow]No organizations found.[/]")
        raise typer.Exit()

    table = Table(title=f"Organizations ({len(orgs_list)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="cyan", max_width=35)
    table.add_column("Domain", style="white", max_width=30)

    for org in orgs_list:
        org_id = str(org.get("id", ""))
        name = org.get("name", "")
        domain = org.get("domain", "") or ""
        table.add_row(org_id, name, domain)

    console.print(table)


@app.command()
def organization(
    org_id: int = typer.Argument(..., help="Organization ID"),
    interactions: bool = typer.Option(False, "--interactions", "-i", help="Include interactions"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get organization details."""
    from .client import _client

    client = _client()
    data = client.get_organization(org_id, with_interaction_dates=interactions)

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    console.print(f"[bold]Name:[/] {data.get('name', 'N/A')}")
    console.print(f"[bold]ID:[/] {data.get('id', 'N/A')}")
    console.print(f"[bold]Domain:[/] {data.get('domain', 'N/A')}")

    domains = data.get("domains", [])
    if domains:
        console.print(f"[bold]All Domains:[/] {', '.join(domains)}")

    person_ids = data.get("person_ids", [])
    if person_ids:
        console.print(f"[bold]Person IDs:[/] {', '.join(map(str, person_ids[:10]))}")
        if len(person_ids) > 10:
            console.print(f"  [dim]... and {len(person_ids) - 10} more[/]")

    if interactions:
        dates = data.get("interaction_dates", {})
        if dates:
            console.print("\n[bold]Interactions:[/]")
            for key, val in dates.items():
                if val:
                    console.print(f"  {key}: {val}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(25, "--limit", "-n", help="Max results per type"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search across persons and organizations."""
    from .client import _client

    client = _client()
    persons_data = client.search_persons(term=query, page_size=limit)
    orgs_data = client.search_organizations(term=query, page_size=limit)

    if json_output:
        result = {
            "persons": persons_data.get("persons", []),
            "organizations": orgs_data.get("organizations", []),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stdout)
        raise typer.Exit()

    persons_list = persons_data.get("persons", [])
    orgs_list = orgs_data.get("organizations", [])

    if persons_list:
        console.print(f"\n[bold]Persons ({len(persons_list)}):[/]")
        for p in persons_list[:10]:
            first = p.get("first_name", "") or ""
            last = p.get("last_name", "") or ""
            email = p.get("primary_email", "") or ""
            console.print(f"  [cyan]{p.get('id')}[/] {first} {last} - {email}")

    if orgs_list:
        console.print(f"\n[bold]Organizations ({len(orgs_list)}):[/]")
        for o in orgs_list[:10]:
            domain = o.get("domain", "") or ""
            console.print(f"  [cyan]{o.get('id')}[/] {o.get('name', '')} - {domain}")

    if not persons_list and not orgs_list:
        console.print("[yellow]No results found.[/]")


@app.command()
def raw(
    endpoint: str = typer.Argument(..., help="API endpoint (e.g., /lists)"),
    method: str = typer.Option("GET", "--method", "-X", help="HTTP method"),
    data: str = typer.Option(None, "--data", "-d", help="JSON payload"),
):
    """Make raw API call."""
    from .client import _client

    client = _client()
    payload = json.loads(data) if data else None
    result = client.raw_request(method, endpoint, data=payload)
    print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stdout)


if __name__ == "__main__":
    app()
