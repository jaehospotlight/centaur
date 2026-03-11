"""CLI for Nano Banana (Gemini image generation)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .client import DEFAULT_MODEL, MODELS

load_dotenv()

app = typer.Typer(name="nano-banana", help="Nano Banana CLI for Google Gemini image generation")
console = Console()


def get_client():
    from .client import NanoBananaClient

    return NanoBananaClient()


def write_result_image(payload_json: str, output: Path) -> dict:
    payload = json.loads(payload_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(payload["content_base64"]))
    return payload


@app.command()
def generate(
    prompt: str = typer.Argument(..., help="Text description of the image to generate"),
    output: Path = typer.Option(Path("output.png"), "--output", "-o", help="Output file path"),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Model to use: 'flash' (Nano Banana 2) or 'pro' (Nano Banana Pro)",
    ),
    aspect_ratio: str = typer.Option(
        None,
        "--aspect-ratio",
        "-a",
        help="Aspect ratio: 1:1, 3:4, 4:3, 9:16, 16:9",
    ),
    size: str = typer.Option(
        None,
        "--size",
        "-s",
        help="Optional image size, typically used with the pro model (for example: 1K, 2K, 4K)",
    ),
    person_generation: str = typer.Option(
        None,
        "--person-generation",
        help="DONT_ALLOW, ALLOW_ADULT, or ALLOW_ALL",
    ),
    search: bool = typer.Option(
        False,
        "--search",
        help="Enable Google Search grounding when supported by the selected model",
    ),
    thinking_budget: int = typer.Option(
        None,
        "--thinking-budget",
        help="Optional thinking budget for supported models",
    ),
    thinking_level: str = typer.Option(
        None,
        "--thinking-level",
        help="Optional thinking level: minimal, low, medium, or high",
    ),
):
    """Generate an image from a text prompt."""
    client = get_client()

    with console.status(f"[bold green]Generating image with {model} model..."):
        try:
            payload = write_result_image(
                client.generate(
                    prompt=prompt,
                    model=model,
                    aspect_ratio=aspect_ratio,
                    image_size=size,
                    person_generation=person_generation,
                    use_google_search=search,
                    thinking_budget=thinking_budget,
                    thinking_level=thinking_level,
                    filename=output.name,
                ),
                output,
            )
            console.print(f"[green]✓[/] Image saved to [cyan]{output}[/]")
            if payload.get("text_response"):
                console.print(f"[dim]{payload['text_response']}[/]")
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)


@app.command()
def edit(
    image: Path = typer.Argument(..., help="Path to the input image to edit"),
    prompt: str = typer.Argument(..., help="Text description of the edit to make"),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file path (defaults to input_edited.png)"
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Model to use: 'flash' (Nano Banana 2) or 'pro' (Nano Banana Pro)",
    ),
    aspect_ratio: str = typer.Option(
        None,
        "--aspect-ratio",
        "-a",
        help="Aspect ratio: 1:1, 3:4, 4:3, 9:16, 16:9",
    ),
    size: str = typer.Option(
        None,
        "--size",
        "-s",
        help="Optional image size, typically used with the pro model (for example: 1K, 2K, 4K)",
    ),
    person_generation: str = typer.Option(
        None,
        "--person-generation",
        help="DONT_ALLOW, ALLOW_ADULT, or ALLOW_ALL",
    ),
    search: bool = typer.Option(
        False,
        "--search",
        help="Enable Google Search grounding when supported by the selected model",
    ),
    thinking_budget: int = typer.Option(
        None,
        "--thinking-budget",
        help="Optional thinking budget for supported models",
    ),
    thinking_level: str = typer.Option(
        None,
        "--thinking-level",
        help="Optional thinking level: minimal, low, medium, or high",
    ),
):
    """Edit an existing image based on a text prompt."""
    if not image.exists():
        console.print(f"[red]Error:[/] Image not found: {image}")
        raise typer.Exit(1)

    if output is None:
        output = image.with_stem(f"{image.stem}_edited")

    client = get_client()

    with console.status(f"[bold green]Editing image with {model} model..."):
        try:
            payload = write_result_image(
                client.edit(
                    prompt=prompt,
                    image_path=str(image),
                    model=model,
                    aspect_ratio=aspect_ratio,
                    image_size=size,
                    person_generation=person_generation,
                    use_google_search=search,
                    thinking_budget=thinking_budget,
                    thinking_level=thinking_level,
                    filename=output.name,
                ),
                output,
            )
            console.print(f"[green]✓[/] Edited image saved to [cyan]{output}[/]")
            if payload.get("text_response"):
                console.print(f"[dim]{payload['text_response']}[/]")
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)


@app.command()
def models():
    """List available image generation models."""
    table = Table(title="Available Models")
    table.add_column("Name", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Model ID", style="yellow")
    table.add_column("Description", style="dim")

    for name, info in MODELS.items():
        table.add_row(name, info["label"], info["id"], info["description"])

    console.print(table)
    console.print("\n[dim]Use --model flash or --model pro with generate/edit commands.[/]")


if __name__ == "__main__":
    app()
