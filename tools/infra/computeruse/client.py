"""ComputerUse client — QEMU Windows VMs driven with computer-use actions over VNC.

Lifecycle: ``spawn_vm`` boots a copy-on-write overlay of a golden Windows qcow2
image (downloaded once to ``~/.computeruse/cache/``) and exposes a local VNC
port. Actions (``click``, ``type_text``, ``key``, ``scroll``, ``drag``) connect
to that VNC port on demand and disconnect afterwards. Actions are deliberately
cheap and do not capture the screen — the agent loop is: action → ``screenshot``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image
from vncdotool import api as vnc_api

from centaur_sdk import secret

BASE_DIR = Path.home() / ".computeruse"
VMS_DIR = BASE_DIR / "vms"
CACHE_DIR = BASE_DIR / "cache"
RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

QEMU_BINARY = "qemu-system-x86_64"
QEMU_IMG_BINARY = "qemu-img"
VNC_BASE_PORT = 5900
# VNC display numbers we allocate from; display 20 -> VNC port 5920.
DISPLAY_RANGE = range(20, 100)
# RDP forward port derived from the display so the first VM gets 3390.
RDP_PORT_OFFSET = 3370

KVM_ACCEL_NOTE = "kvm"
TCG_ACCEL_NOTE = (
    "tcg (software emulation — expect a slow VM; ask infra to enable KVM on sandbox pods)"
)

OVMF_DIR = Path("/usr/share/OVMF")
# (code, vars-template) pairs, preferred first. The ``.ms`` variants carry the
# Microsoft secure-boot keys Windows 11 wants.
OVMF_CANDIDATES = (
    ("OVMF_CODE_4M.ms.fd", "OVMF_VARS_4M.ms.fd"),
    ("OVMF_CODE_4M.fd", "OVMF_VARS_4M.fd"),
    ("OVMF_CODE.ms.fd", "OVMF_VARS.ms.fd"),
    ("OVMF_CODE.fd", "OVMF_VARS.fd"),
)

MOUSE_BUTTONS = {"left": 1, "middle": 2, "right": 3}
SCROLL_BUTTONS = {"up": 4, "down": 5}
# Friendly aliases -> vncdotool KEYMAP names (see vncdotool.client.KEYMAP).
KEY_ALIASES = {
    "win": "super",
    "windows": "super",
    "cmd": "super",
    "control": "ctrl",
    "option": "alt",
    "escape": "esc",
    "backspace": "bsp",
    "pageup": "pgup",
    "pagedown": "pgdn",
    "insert": "ins",
}
# Characters that must be sent as named keys when typing text.
TYPE_KEYS = {"\n": "enter", "\r": "enter", "\t": "tab"}


def _build_qemu_cmd(
    *,
    name: str,
    disk_path: str,
    cpus: int,
    memory_gb: int,
    vnc_display: int,
    rdp_port: int,
    qmp_sock: str,
    pidfile: str,
    serial_log: str,
    qemu_log: str,
    accel: str,
    width: int,
    height: int,
    ovmf_code: str | None = None,
    ovmf_vars: str | None = None,
    tpm_sock: str | None = None,
    cdroms: tuple[str, ...] = (),
    boot_cd: bool = False,
) -> list[str]:
    """Build the qemu-system-x86_64 argv (pure — no filesystem side effects).

    ``accel`` is ``"kvm"`` or ``"tcg"``. ``ovmf_code``/``ovmf_vars`` enable UEFI
    pflash, ``tpm_sock`` wires a swtpm socket TPM, ``cdroms`` attach extra ISO
    media (installer, virtio drivers, autounattend) and ``boot_cd`` boots from
    CD once for installs.
    """
    cmd = [
        QEMU_BINARY,
        "-name",
        name,
        "-machine",
        "q35",
        "-smp",
        str(cpus),
        "-m",
        f"{memory_gb}G",
    ]
    if accel == "kvm":
        cmd += ["-accel", "kvm", "-cpu", "host"]
    else:
        cmd += ["-accel", "tcg,thread=multi", "-cpu", "qemu64"]
    if ovmf_code and ovmf_vars:
        cmd += [
            "-drive",
            f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
            "-drive",
            f"if=pflash,format=raw,file={ovmf_vars}",
        ]
    cmd += [
        "-drive",
        f"file={disk_path},if=virtio,format=qcow2,discard=unmap",
        "-netdev",
        f"user,id=net0,hostfwd=tcp:127.0.0.1:{rdp_port}-:3389",
        "-device",
        "virtio-net-pci,netdev=net0",
        # virtio-vga honors xres/yres as the preferred guest resolution.
        "-device",
        f"virtio-vga,xres={width},yres={height}",
        # usb-tablet gives absolute pointer coordinates so VNC clicks land
        # exactly where the screenshot says they should.
        "-usb",
        "-device",
        "usb-tablet",
        "-vnc",
        f"127.0.0.1:{vnc_display}",
        "-qmp",
        f"unix:{qmp_sock},server,nowait",
        "-pidfile",
        pidfile,
        "-serial",
        f"file:{serial_log}",
        "-D",
        qemu_log,
        "-daemonize",
    ]
    if tpm_sock:
        cmd += [
            "-chardev",
            f"socket,id=chrtpm,path={tpm_sock}",
            "-tpmdev",
            "emulator,id=tpm0,chardev=chrtpm",
            "-device",
            "tpm-tis,tpmdev=tpm0",
        ]
    for iso in cdroms:
        cmd += ["-drive", f"file={iso},media=cdrom,readonly=on"]
    if boot_cd:
        cmd += ["-boot", "once=d"]
    return cmd


def _find_ovmf() -> tuple[str, str] | None:
    """Return (OVMF_CODE, OVMF_VARS template) paths if UEFI firmware exists."""
    if not OVMF_DIR.is_dir():
        return None
    for code, vars_tmpl in OVMF_CANDIDATES:
        code_path = OVMF_DIR / code
        vars_path = OVMF_DIR / vars_tmpl
        if code_path.is_file() and vars_path.is_file():
            return str(code_path), str(vars_path)
    return None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class ComputerUseClient:
    """Spawn Windows VMs via QEMU and drive them with computer-use actions over VNC."""

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _state_dir(self, name: str, create: bool = False) -> Path:
        path = VMS_DIR / name
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _state_path(self, name: str) -> Path:
        return self._state_dir(name) / "state.json"

    def _read_state(self, name: str) -> dict | None:
        path = self._state_path(name)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text())
        except ValueError:
            return None

    def _write_state(self, name: str, state: dict) -> None:
        self._state_path(name).write_text(json.dumps(state, indent=2))

    def _pid_from_file(self, path: Path) -> int | None:
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return None

    def _pid_alive(self, pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _qemu_pid(self, name: str) -> int | None:
        pid = self._pid_from_file(self._state_dir(name) / "qemu.pid")
        return pid if self._pid_alive(pid) else None

    def _require_qemu(self) -> None:
        if shutil.which(QEMU_BINARY) is None:
            raise RuntimeError(
                f"{QEMU_BINARY} not found on PATH. The sandbox image must include QEMU "
                "(qemu-system-x86, qemu-utils) for computeruse to spawn Windows VMs."
            )
        if shutil.which(QEMU_IMG_BINARY) is None:
            raise RuntimeError(
                f"{QEMU_IMG_BINARY} not found on PATH. Install qemu-utils in the sandbox image."
            )

    def _detect_accel(self) -> tuple[str, str]:
        """Return (accel flag, human note) — KVM if /dev/kvm is usable, else TCG."""
        if os.access("/dev/kvm", os.R_OK | os.W_OK):
            return "kvm", KVM_ACCEL_NOTE
        return "tcg", TCG_ACCEL_NOTE

    def _find_free_display(self) -> int:
        used = {
            state.get("vnc_display")
            for state in (self._read_state(p.name) for p in self._iter_vm_dirs())
            if state and self._qemu_pid(state.get("name", "")) is not None
        }
        for display in DISPLAY_RANGE:
            if display in used:
                continue
            if _port_free(VNC_BASE_PORT + display) and _port_free(RDP_PORT_OFFSET + display):
                return display
        raise RuntimeError("No free VNC display found in range 20-99; stop some VMs first.")

    def _iter_vm_dirs(self) -> list[Path]:
        if not VMS_DIR.is_dir():
            return []
        return sorted(p for p in VMS_DIR.iterdir() if p.is_dir())

    def _resolve_image_url(self, image_url: str | None) -> str:
        url = image_url or secret("COMPUTERUSE_WINDOWS_IMAGE_URL", "")
        if not url:
            raise RuntimeError(
                "No Windows golden image configured. Pass image_url or set "
                "COMPUTERUSE_WINDOWS_IMAGE_URL to an https URL of a prebuilt Windows "
                "qcow2 image (build one with install_vm + resources/autounattend.xml)."
            )
        return url

    def _ensure_cached_image(self, url: str) -> Path:
        """Download the golden qcow2 to the shared cache (idempotent)."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        basename = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "image.qcow2"
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        cached = CACHE_DIR / f"{digest}-{basename}"
        if cached.is_file() and cached.stat().st_size > 0:
            return cached
        partial = cached.with_suffix(cached.suffix + ".part")
        try:
            with (
                httpx.Client(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=True) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                with open(partial, "wb") as fh:
                    for chunk in response.iter_bytes(chunk_size=1 << 20):
                        fh.write(chunk)
        except httpx.HTTPStatusError as e:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"Failed to download golden image: {e.response.status_code} from {url}"
            ) from e
        except httpx.RequestError as e:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download golden image from {url}: {e}") from e
        partial.rename(cached)
        return cached

    def _create_overlay(self, backing: Path, disk: Path) -> None:
        """Create a copy-on-write overlay so the golden image is never mutated."""
        result = subprocess.run(
            [
                QEMU_IMG_BINARY,
                "create",
                "-f",
                "qcow2",
                "-b",
                str(backing),
                "-F",
                "qcow2",
                str(disk),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"qemu-img create failed: {result.stderr.strip()}")

    def _start_swtpm(self, state_dir: Path) -> str | None:
        """Start a swtpm socket TPM for the VM; return its socket path or None."""
        if shutil.which("swtpm") is None:
            return None
        tpm_state = state_dir / "tpm"
        tpm_state.mkdir(parents=True, exist_ok=True)
        tpm_sock = state_dir / "swtpm.sock"
        tpm_pidfile = state_dir / "swtpm.pid"
        result = subprocess.run(
            [
                "swtpm",
                "socket",
                "--tpm2",
                "--tpmstate",
                f"dir={tpm_state}",
                "--ctrl",
                f"type=unixio,path={tpm_sock}",
                "--pid",
                f"file={tpm_pidfile}",
                "--log",
                f"file={state_dir / 'swtpm.log'},level=1",
                "--daemon",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        for _ in range(50):
            if tpm_sock.exists():
                return str(tpm_sock)
            time.sleep(0.1)
        return None

    def _stop_swtpm(self, name: str) -> None:
        pidfile = self._state_dir(name) / "swtpm.pid"
        pid = self._pid_from_file(pidfile)
        if pid and self._pid_alive(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        pidfile.unlink(missing_ok=True)

    def _qmp(self, name: str, command: str) -> dict | None:
        """Send a single QMP command to the VM's monitor socket; None if unreachable."""
        sock_path = self._state_dir(name) / "qmp.sock"
        if not sock_path.exists():
            return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)
                sock.connect(str(sock_path))
                stream = sock.makefile("rwb")
                stream.readline()  # QMP greeting banner
                reply: dict = {}
                for payload in ({"execute": "qmp_capabilities"}, {"execute": command}):
                    stream.write(json.dumps(payload).encode() + b"\n")
                    stream.flush()
                    for _ in range(10):  # skip async events until a reply arrives
                        line = stream.readline()
                        if not line:
                            return None
                        reply = json.loads(line)
                        if "return" in reply or "error" in reply:
                            break
                return reply.get("return", {})
        except (OSError, ValueError):
            return None

    def _launch_qemu(self, cmd: list[str], state_dir: Path) -> int:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"QEMU failed to start: {result.stderr.strip() or result.stdout.strip()}"
            )
        pidfile = state_dir / "qemu.pid"
        for _ in range(50):
            pid = self._pid_from_file(pidfile)
            if pid and self._pid_alive(pid):
                return pid
            time.sleep(0.1)
        raise RuntimeError(f"QEMU daemonized but no live pid found in {pidfile}")

    def _running_state(self, name: str) -> dict:
        """Return the recorded state for a running VM, or raise."""
        state = self._read_state(name)
        if state is None:
            raise RuntimeError(f"No VM named {name!r}. Spawn it first with spawn_vm.")
        if self._qemu_pid(name) is None:
            raise RuntimeError(f"VM {name!r} is not running. Spawn it first with spawn_vm.")
        return state

    def _vnc_connect(self, name: str):
        state = self._running_state(name)
        addr = f"127.0.0.1::{state['vnc_port']}"
        try:
            return vnc_api.connect(addr, password=None, timeout=30)
        except Exception as e:  # twisted raises a zoo of connection errors
            raise RuntimeError(f"Could not connect to VNC for VM {name!r} at {addr}: {e}") from e

    def _vnc_disconnect(self, client) -> None:
        with contextlib.suppress(Exception):
            client.disconnect()

    def _normalize_combo(self, combo: str) -> str:
        parts = [p for p in combo.replace("+", "-").split("-") if p]
        if not parts:
            raise RuntimeError(f"Empty key combo: {combo!r}")
        normalized = []
        for part in parts:
            token = part.lower() if len(part) > 1 else part
            normalized.append(KEY_ALIASES.get(token, token))
        return "-".join(normalized)

    # ------------------------------------------------------------------
    # VM lifecycle
    # ------------------------------------------------------------------

    def spawn_vm(
        self,
        name: str = "win",
        cpus: int = 4,
        memory_gb: int = 8,
        image_url: str | None = None,
        display_size: str = "1280x800",
        fresh: bool = False,
    ) -> dict:
        """Spawn a Windows VM from the golden qcow2 image and expose it over VNC.

        Downloads the golden image (COMPUTERUSE_WINDOWS_IMAGE_URL or image_url) to a
        shared cache on first use, boots a copy-on-write overlay so the golden image
        is never mutated, and returns connection details. If a VM with this name is
        already running and fresh is False, returns its status instead. fresh=True
        stops any running VM and recreates the overlay disk from the golden image.
        """
        self._require_qemu()
        state_dir = self._state_dir(name, create=True)

        if self._qemu_pid(name) is not None:
            if not fresh:
                return self.vm_status(name)
            self.stop_vm(name, force=True)

        try:
            width, height = (int(v) for v in display_size.lower().split("x"))
        except ValueError as e:
            raise RuntimeError(f"Invalid display_size {display_size!r}; expected WIDTHxHEIGHT") from e

        url = self._resolve_image_url(image_url)
        golden = self._ensure_cached_image(url)
        disk = state_dir / "disk.qcow2"
        if fresh:
            disk.unlink(missing_ok=True)
        if not disk.is_file():
            self._create_overlay(golden, disk)

        display = self._find_free_display()
        vnc_port = VNC_BASE_PORT + display
        rdp_port = RDP_PORT_OFFSET + display
        accel, accel_note = self._detect_accel()
        notes: list[str] = []

        ovmf = _find_ovmf()
        ovmf_code = ovmf_vars = None
        if ovmf:
            ovmf_code, vars_template = ovmf
            vars_copy = state_dir / "OVMF_VARS.fd"
            if fresh or not vars_copy.is_file():
                shutil.copyfile(vars_template, vars_copy)
            ovmf_vars = str(vars_copy)
        else:
            notes.append("OVMF not found — booting legacy BIOS (Windows 11 images may not boot)")

        tpm_sock = self._start_swtpm(state_dir)
        if tpm_sock is None:
            notes.append("swtpm not available — no TPM device (Windows 11 images may complain)")

        cmd = _build_qemu_cmd(
            name=name,
            disk_path=str(disk),
            cpus=cpus,
            memory_gb=memory_gb,
            vnc_display=display,
            rdp_port=rdp_port,
            qmp_sock=str(state_dir / "qmp.sock"),
            pidfile=str(state_dir / "qemu.pid"),
            serial_log=str(state_dir / "serial.log"),
            qemu_log=str(state_dir / "qemu.log"),
            accel=accel,
            width=width,
            height=height,
            ovmf_code=ovmf_code,
            ovmf_vars=ovmf_vars,
            tpm_sock=tpm_sock,
        )
        try:
            pid = self._launch_qemu(cmd, state_dir)
        except RuntimeError:
            self._stop_swtpm(name)
            raise

        state = {
            "name": name,
            "pid": pid,
            "vnc_display": display,
            "vnc_port": vnc_port,
            "rdp_port": rdp_port,
            "accel": accel,
            "disk": str(disk),
            "image_url": url,
            "display_size": display_size,
            "cpus": cpus,
            "memory_gb": memory_gb,
            "uefi": bool(ovmf),
            "tpm": bool(tpm_sock),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._write_state(name, state)
        return {
            "name": name,
            "state": "running",
            "pid": pid,
            "vnc_port": vnc_port,
            "rdp_port": rdp_port,
            "accel": accel_note,
            "disk": str(disk),
            "display_size": display_size,
            "notes": notes,
        }

    def vm_status(self, name: str = "win") -> dict:
        """Report status for a named VM: pid liveness plus QMP query-status if reachable."""
        state = self._read_state(name)
        if state is None:
            return {"name": name, "state": "absent"}
        pid = self._qemu_pid(name)
        qmp_status = self._qmp(name, "query-status") if pid else None
        return {
            **state,
            "pid": pid,
            "state": "running" if pid else "stopped",
            "qmp_status": (qmp_status or {}).get("status") if qmp_status else None,
            "accel": TCG_ACCEL_NOTE if state.get("accel") == "tcg" else state.get("accel"),
        }

    def list_vms(self) -> list[dict]:
        """List all known VMs (running and stopped) with their status."""
        return [self.vm_status(path.name) for path in self._iter_vm_dirs()]

    def stop_vm(self, name: str = "win", force: bool = False) -> dict:
        """Stop a VM: QMP system_powerdown (graceful), falling back to SIGTERM/SIGKILL.

        force=True skips the graceful ACPI shutdown and kills QEMU immediately.
        Also stops the VM's swtpm process and cleans up pidfiles/sockets.
        """
        state_dir = self._state_dir(name)
        if not state_dir.is_dir():
            raise RuntimeError(f"No VM named {name!r}.")
        pid = self._qemu_pid(name)
        method = "already-stopped"
        if pid:
            if not force:
                self._qmp(name, "system_powerdown")
                method = "powerdown"
                deadline = time.time() + 30
                while time.time() < deadline and self._pid_alive(pid):
                    time.sleep(0.5)
            if self._pid_alive(pid):
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGTERM)
                method = "sigterm"
                deadline = time.time() + 10
                while time.time() < deadline and self._pid_alive(pid):
                    time.sleep(0.5)
            if self._pid_alive(pid):
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
                method = "sigkill"
        self._stop_swtpm(name)
        (state_dir / "qemu.pid").unlink(missing_ok=True)
        (state_dir / "qmp.sock").unlink(missing_ok=True)
        (state_dir / "swtpm.sock").unlink(missing_ok=True)
        return {"name": name, "state": "stopped", "method": method}

    def install_vm(
        self,
        iso_path: str,
        name: str = "win-install",
        disk_gb: int = 64,
        cpus: int = 4,
        memory_gb: int = 8,
        display_size: str = "1280x800",
        virtio_iso: str | None = None,
        autounattend: str | None = None,
        fresh: bool = False,
    ) -> dict:
        """Boot a Windows installer ISO against a blank disk to build a golden image.

        One-time helper: attach the Windows ISO (and optionally a virtio-win drivers
        ISO plus an autounattend ISO built from resources/autounattend.xml) to a new
        sparse qcow2, boot from CD, and watch/drive the install over VNC. When the
        install finishes, stop the VM and upload the disk as the golden image behind
        COMPUTERUSE_WINDOWS_IMAGE_URL. autounattend accepts a prebuilt .iso, or a
        .xml that is wrapped into an ISO if genisoimage/mkisofs/xorrisofs exists.
        """
        self._require_qemu()
        iso = Path(iso_path).expanduser()
        if not iso.is_file():
            raise RuntimeError(f"Installer ISO not found: {iso}")
        state_dir = self._state_dir(name, create=True)
        if self._qemu_pid(name) is not None:
            if not fresh:
                return self.vm_status(name)
            self.stop_vm(name, force=True)

        try:
            width, height = (int(v) for v in display_size.lower().split("x"))
        except ValueError as e:
            raise RuntimeError(f"Invalid display_size {display_size!r}; expected WIDTHxHEIGHT") from e

        disk = state_dir / "disk.qcow2"
        if fresh:
            disk.unlink(missing_ok=True)
        if not disk.is_file():
            result = subprocess.run(
                [QEMU_IMG_BINARY, "create", "-f", "qcow2", str(disk), f"{disk_gb}G"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"qemu-img create failed: {result.stderr.strip()}")

        cdroms = [str(iso)]
        if virtio_iso:
            virtio = Path(virtio_iso).expanduser()
            if not virtio.is_file():
                raise RuntimeError(f"virtio-win ISO not found: {virtio}")
            cdroms.append(str(virtio))
        if autounattend:
            cdroms.append(str(self._autounattend_iso(Path(autounattend).expanduser(), state_dir)))

        display = self._find_free_display()
        vnc_port = VNC_BASE_PORT + display
        rdp_port = RDP_PORT_OFFSET + display
        accel, accel_note = self._detect_accel()
        notes: list[str] = []

        ovmf = _find_ovmf()
        ovmf_code = ovmf_vars = None
        if ovmf:
            ovmf_code, vars_template = ovmf
            vars_copy = state_dir / "OVMF_VARS.fd"
            if fresh or not vars_copy.is_file():
                shutil.copyfile(vars_template, vars_copy)
            ovmf_vars = str(vars_copy)
        else:
            notes.append("OVMF not found — booting legacy BIOS (Windows 11 setup may refuse)")
        tpm_sock = self._start_swtpm(state_dir)
        if tpm_sock is None:
            notes.append("swtpm not available — no TPM device (Windows 11 setup may refuse)")

        cmd = _build_qemu_cmd(
            name=name,
            disk_path=str(disk),
            cpus=cpus,
            memory_gb=memory_gb,
            vnc_display=display,
            rdp_port=rdp_port,
            qmp_sock=str(state_dir / "qmp.sock"),
            pidfile=str(state_dir / "qemu.pid"),
            serial_log=str(state_dir / "serial.log"),
            qemu_log=str(state_dir / "qemu.log"),
            accel=accel,
            width=width,
            height=height,
            ovmf_code=ovmf_code,
            ovmf_vars=ovmf_vars,
            tpm_sock=tpm_sock,
            cdroms=tuple(cdroms),
            boot_cd=True,
        )
        try:
            pid = self._launch_qemu(cmd, state_dir)
        except RuntimeError:
            self._stop_swtpm(name)
            raise
        state = {
            "name": name,
            "pid": pid,
            "vnc_display": display,
            "vnc_port": vnc_port,
            "rdp_port": rdp_port,
            "accel": accel,
            "disk": str(disk),
            "display_size": display_size,
            "cpus": cpus,
            "memory_gb": memory_gb,
            "uefi": bool(ovmf),
            "tpm": bool(tpm_sock),
            "install": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._write_state(name, state)
        return {
            "name": name,
            "state": "running",
            "pid": pid,
            "vnc_port": vnc_port,
            "rdp_port": rdp_port,
            "accel": accel_note,
            "disk": str(disk),
            "cdroms": cdroms,
            "notes": notes,
            "next_steps": (
                "Watch the install with screenshot(); once Windows is installed and "
                f"configured, stop_vm({name!r}) and publish {disk} as the golden image."
            ),
        }

    def _autounattend_iso(self, source: Path, state_dir: Path) -> Path:
        """Return an ISO carrying autounattend.xml, building one from a .xml if needed."""
        if not source.is_file():
            raise RuntimeError(f"autounattend file not found: {source}")
        if source.suffix.lower() == ".iso":
            return source
        tool = next(
            (t for t in ("genisoimage", "mkisofs", "xorrisofs") if shutil.which(t)), None
        )
        if tool is None:
            raise RuntimeError(
                "Cannot build autounattend ISO: none of genisoimage/mkisofs/xorrisofs "
                "found. Provide a prebuilt .iso containing autounattend.xml instead."
            )
        staging = state_dir / "autounattend"
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, staging / "autounattend.xml")
        iso = state_dir / "autounattend.iso"
        result = subprocess.run(
            [tool, "-quiet", "-J", "-r", "-V", "UNATTEND", "-o", str(iso), str(staging)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{tool} failed building autounattend ISO: {result.stderr.strip()}")
        return iso

    # ------------------------------------------------------------------
    # computer-use actions (loop: action -> screenshot)
    # ------------------------------------------------------------------

    def screenshot(self, name: str = "win", output_path: str | None = None) -> dict:
        """Capture the VM screen to a PNG and return its path and dimensions.

        This is the only action that captures the screen; run it after each
        click/type/key/scroll/drag to observe the result.
        """
        state = self._running_state(name)
        if output_path:
            path = Path(output_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            shots = self._state_dir(name) / "screenshots"
            shots.mkdir(parents=True, exist_ok=True)
            path = shots / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.png"
        client = self._vnc_connect(name)
        try:
            client.captureScreen(str(path))
        finally:
            self._vnc_disconnect(client)
        with Image.open(path) as img:
            width, height = img.size
        return {"name": state["name"], "path": str(path), "width": width, "height": height}

    def click(
        self,
        x: int,
        y: int,
        name: str = "win",
        button: str = "left",
        double: bool = False,
    ) -> dict:
        """Click at (x, y). button is left/right/middle; double=True double-clicks.

        Follow with screenshot() to observe the result.
        """
        btn = MOUSE_BUTTONS.get(button)
        if btn is None:
            raise RuntimeError(f"Unknown button {button!r}; use left, right, or middle.")
        client = self._vnc_connect(name)
        try:
            client.mouseMove(x, y)
            client.pause(0.05)
            client.mousePress(btn)
            if double:
                client.pause(0.08)
                client.mousePress(btn)
        finally:
            self._vnc_disconnect(client)
        return {"action": "click", "x": x, "y": y, "button": button, "double": double}

    def move(self, x: int, y: int, name: str = "win") -> dict:
        """Move the mouse pointer to (x, y) without clicking."""
        client = self._vnc_connect(name)
        try:
            client.mouseMove(x, y)
        finally:
            self._vnc_disconnect(client)
        return {"action": "move", "x": x, "y": y}

    def drag(self, x1: int, y1: int, x2: int, y2: int, name: str = "win") -> dict:
        """Drag with the left button from (x1, y1) to (x2, y2)."""
        client = self._vnc_connect(name)
        try:
            client.mouseMove(x1, y1)
            client.pause(0.1)
            client.mouseDown(1)
            client.pause(0.1)
            client.mouseDrag(x2, y2, step=16)
            client.pause(0.1)
            client.mouseUp(1)
        finally:
            self._vnc_disconnect(client)
        return {"action": "drag", "from": [x1, y1], "to": [x2, y2]}

    def type_text(self, text: str, name: str = "win", interval: float = 0.02) -> dict:
        """Type text into the VM, one keypress per character.

        Newlines and tabs are sent as enter/tab. Use key() for shortcuts and
        follow with screenshot() to observe the result.
        """
        client = self._vnc_connect(name)
        try:
            for char in text:
                client.keyPress(TYPE_KEYS.get(char, char))
                if interval > 0:
                    client.pause(interval)
        finally:
            self._vnc_disconnect(client)
        return {"action": "type_text", "chars": len(text)}

    def key(self, combo: str, name: str = "win") -> dict:
        """Press a key or combo, e.g. 'enter', 'ctrl-alt-del', 'win-r', 'alt-f4'.

        Combos join keys with '-' (or '+'); win/cmd map to the Super key.
        Follow with screenshot() to observe the result.
        """
        normalized = self._normalize_combo(combo)
        client = self._vnc_connect(name)
        try:
            client.keyPress(normalized)
        finally:
            self._vnc_disconnect(client)
        return {"action": "key", "combo": combo, "sent": normalized}

    def scroll(
        self,
        x: int,
        y: int,
        direction: str = "down",
        clicks: int = 3,
        name: str = "win",
    ) -> dict:
        """Scroll the wheel at (x, y). direction is up or down; clicks is wheel notches."""
        btn = SCROLL_BUTTONS.get(direction)
        if btn is None:
            raise RuntimeError(f"Unknown scroll direction {direction!r}; use up or down.")
        client = self._vnc_connect(name)
        try:
            client.mouseMove(x, y)
            client.pause(0.05)
            for _ in range(max(1, clicks)):
                client.mousePress(btn)
                client.pause(0.02)
        finally:
            self._vnc_disconnect(client)
        return {"action": "scroll", "x": x, "y": y, "direction": direction, "clicks": clicks}

    def wait(self, seconds: float) -> dict:
        """Sleep up to 60 seconds (e.g. while Windows boots or an app loads)."""
        capped = max(0.0, min(float(seconds), 60.0))
        time.sleep(capped)
        return {"action": "wait", "seconds": capped}


def _client() -> ComputerUseClient:
    return ComputerUseClient()
