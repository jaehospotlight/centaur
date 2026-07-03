"""CLI for computeruse — QEMU Windows VMs with computer-use actions over VNC."""

from dotenv import load_dotenv

load_dotenv()

import json
import os
import shutil

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="computeruse",
    help="Spawn and drive Windows VMs (QEMU) with computer-use actions over VNC",
)


def _teardown():
    """Stop vncdotool's non-daemon reactor thread so the CLI process exits.

    Safe no-op when no VNC connection was made; must only run in this one-shot
    CLI process (a stopped reactor cannot be restarted).
    """
    from .client import _shutdown_vnc

    _shutdown_vnc()


@app.command("health")
def health():
    """Assert computeruse readiness with a safe read-only check."""
    from .client import QEMU_BINARY, _client

    client = _client()
    try:
        details = {
            "qemu": shutil.which(QEMU_BINARY),
            "swtpm": shutil.which("swtpm"),
            "kvm": os.access("/dev/kvm", os.R_OK | os.W_OK),
            "vms": client.list_vms(),
        }
        payload = {"ok": True, "tool": "computeruse", "error": None, "details": details}
    except Exception as exc:
        payload = {"ok": False, "tool": "computeruse", "error": str(exc), "details": {}}
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        raise typer.Exit(1) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


console = Console()


def get_client():
    from .client import ComputerUseClient

    return ComputerUseClient()


def _emit(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


@app.command()
def spawn(
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    cpus: int = typer.Option(4, "--cpus", help="vCPU count"),
    memory_gb: int = typer.Option(8, "--memory-gb", "-m", help="RAM in GiB"),
    image_url: str | None = typer.Option(
        None, "--image-url", help="Golden qcow2 URL (default: COMPUTERUSE_WINDOWS_IMAGE_URL)"
    ),
    display_size: str = typer.Option("1280x800", "--display-size", help="Guest resolution WxH"),
    fresh: bool = typer.Option(False, "--fresh", help="Recreate the overlay disk from scratch"),
):
    """Spawn a Windows VM from the golden image."""
    client = get_client()
    result = client.spawn_vm(
        name=name,
        cpus=cpus,
        memory_gb=memory_gb,
        image_url=image_url,
        display_size=display_size,
        fresh=fresh,
    )
    _emit(result)


@app.command()
def status(
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show status of a named VM."""
    client = get_client()
    data = client.vm_status(name)
    if json_output:
        _emit(data)
        return
    console.print(data)


@app.command("list")
def list_vms(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all known VMs."""
    client = get_client()
    vms = client.list_vms()
    if json_output:
        _emit(vms)
        return
    table = Table(title="computeruse VMs")
    for col in ("name", "state", "pid", "vnc_port", "rdp_port", "accel"):
        table.add_column(col)
    for vm in vms:
        table.add_row(*(str(vm.get(col, "")) for col in ("name", "state", "pid", "vnc_port", "rdp_port", "accel")))
    console.print(table)


@app.command()
def stop(
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    force: bool = typer.Option(False, "--force", help="Kill immediately instead of ACPI shutdown"),
):
    """Stop a VM (graceful ACPI powerdown, escalating to SIGTERM/SIGKILL)."""
    client = get_client()
    _emit(client.stop_vm(name, force=force))


@app.command()
def install(
    iso_path: str = typer.Argument(..., help="Windows installer ISO path"),
    name: str = typer.Option("win-install", "--name", "-n", help="VM name"),
    disk_gb: int = typer.Option(64, "--disk-gb", help="Blank disk size in GiB (sparse)"),
    cpus: int = typer.Option(4, "--cpus", help="vCPU count"),
    memory_gb: int = typer.Option(8, "--memory-gb", "-m", help="RAM in GiB"),
    display_size: str = typer.Option("1280x800", "--display-size", help="Guest resolution WxH"),
    virtio_iso: str | None = typer.Option(
        None, "--virtio-iso", help="virtio-win drivers ISO path"
    ),
    autounattend: str | None = typer.Option(
        None,
        "--autounattend",
        help="autounattend .xml or prebuilt .iso (see resources/autounattend.xml)",
    ),
    fresh: bool = typer.Option(False, "--fresh", help="Recreate the install disk from scratch"),
):
    """Boot a Windows installer ISO to build a golden image (one-time helper)."""
    client = get_client()
    result = client.install_vm(
        iso_path=iso_path,
        name=name,
        disk_gb=disk_gb,
        cpus=cpus,
        memory_gb=memory_gb,
        display_size=display_size,
        virtio_iso=virtio_iso,
        autounattend=autounattend,
        fresh=fresh,
    )
    _emit(result)


@app.command()
def screenshot(
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    output: str | None = typer.Option(None, "--output", "-o", help="PNG output path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Capture the VM screen to a PNG."""
    client = get_client()
    data = client.screenshot(name, output_path=output)
    if json_output:
        _emit(data)
        return
    console.print(f"[green]{data['path']}[/] ({data['width']}x{data['height']})")


@app.command()
def click(
    x: int = typer.Argument(..., help="X coordinate"),
    y: int = typer.Argument(..., help="Y coordinate"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    button: str = typer.Option("left", "--button", "-b", help="left, right, or middle"),
    double: bool = typer.Option(False, "--double", help="Double-click"),
):
    """Click at (x, y) in the VM."""
    client = get_client()
    _emit(client.click(x, y, name=name, button=button, double=double))


@app.command()
def move(
    x: int = typer.Argument(..., help="X coordinate"),
    y: int = typer.Argument(..., help="Y coordinate"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
):
    """Move the mouse pointer to (x, y)."""
    client = get_client()
    _emit(client.move(x, y, name=name))


@app.command()
def drag(
    x1: int = typer.Argument(..., help="Start X"),
    y1: int = typer.Argument(..., help="Start Y"),
    x2: int = typer.Argument(..., help="End X"),
    y2: int = typer.Argument(..., help="End Y"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
):
    """Drag with the left button from (x1, y1) to (x2, y2)."""
    client = get_client()
    _emit(client.drag(x1, y1, x2, y2, name=name))


@app.command("type")
def type_text(
    text: str = typer.Argument(..., help="Text to type"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
    interval: float = typer.Option(0.02, "--interval", help="Seconds between keypresses"),
):
    """Type text into the VM."""
    client = get_client()
    _emit(client.type_text(text, name=name, interval=interval))


@app.command()
def key(
    combo: str = typer.Argument(..., help="Key or combo, e.g. enter, ctrl-alt-del, win-r"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
):
    """Press a key or key combo in the VM."""
    client = get_client()
    _emit(client.key(combo, name=name))


@app.command()
def scroll(
    x: int = typer.Argument(..., help="X coordinate"),
    y: int = typer.Argument(..., help="Y coordinate"),
    direction: str = typer.Option("down", "--direction", "-d", help="up or down"),
    clicks: int = typer.Option(3, "--clicks", "-c", help="Wheel notches"),
    name: str = typer.Option("win", "--name", "-n", help="VM name"),
):
    """Scroll the mouse wheel at (x, y)."""
    client = get_client()
    _emit(client.scroll(x, y, direction=direction, clicks=clicks, name=name))


@app.command()
def wait(
    seconds: float = typer.Argument(..., help="Seconds to sleep (capped at 60)"),
):
    """Sleep up to 60 seconds (e.g. while Windows boots)."""
    client = get_client()
    _emit(client.wait(seconds))


def main():
    """Console-script entrypoint: run the app, then stop the VNC reactor even on
    errors so this one-shot process always exits."""
    try:
        app()
    finally:
        _teardown()


if __name__ == "__main__":
    main()
