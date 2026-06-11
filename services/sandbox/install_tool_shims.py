#!/usr/bin/env python3
"""Install shell shims for mounted Centaur tool packages."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib


def _split_paths(value: str) -> list[Path]:
    return [Path(part) for part in value.split(":") if part]


def _git_env() -> tuple[dict[str, str], tempfile.TemporaryDirectory[str] | None]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    token_file = os.environ.get("CENTAUR_TOOLS_GITHUB_TOKEN_FILE")
    if not token_file:
        return env, None
    temp_dir = tempfile.TemporaryDirectory(prefix="centaur-tools-askpass-")
    askpass = Path(temp_dir.name) / "askpass.sh"
    askpass.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) echo x-access-token;;\n"
        f"  *Password*) cat {shlex.quote(token_file)};;\n"
        "  *) echo;;\n"
        "esac\n"
    )
    askpass.chmod(0o700)
    env["GIT_ASKPASS"] = str(askpass)
    return env, temp_dir


def _clear_published_tools(tool_dir: Path) -> None:
    for child in tool_dir.iterdir():
        if child.name in {".centaur-source", ".centaur-tools-source.json"} or child.name.startswith(
            ".centaur-source-"
        ):
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_published_tools(tool_dir: Path, published: Path) -> None:
    if not published.is_dir():
        raise RuntimeError(f"refreshed tools subdir does not exist: {published}")

    for child in published.iterdir():
        target = tool_dir / child.name
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target, follow_symlinks=False)


def _publish_tools(tool_dir: Path, published: Path) -> None:
    _clear_published_tools(tool_dir)
    _copy_published_tools(tool_dir, published)


def _refresh_source(tool_dir: Path, source_metadata: dict[str, object]) -> None:
    subdir = str(source_metadata.get("source_subdir") or "tools")
    if source_metadata.get("source") == "repo_cache":
        repo_cache_repo_path = source_metadata.get("repo_cache_repo_path")
        if not repo_cache_repo_path:
            raise RuntimeError("repo-cache tools metadata is missing repo_cache_repo_path")
        _copy_published_tools(tool_dir, Path(str(repo_cache_repo_path)) / subdir)
        return

    source_path = Path(str(source_metadata.get("source_path") or tool_dir / ".centaur-source"))
    if not source_path.is_dir():
        raise RuntimeError(f"git tools source does not exist: {source_path}")

    git_ref = source_metadata.get("git_ref")
    env, temp_dir = _git_env()
    try:
        if git_ref:
            subprocess.run(
                ["git", "-C", str(source_path), "-c", "gc.auto=0", "fetch", "--quiet", "origin", str(git_ref)],
                check=True,
                env=env,
            )
            subprocess.run(
                ["git", "-C", str(source_path), "checkout", "--quiet", "--detach", "FETCH_HEAD"],
                check=True,
                env=env,
            )
        else:
            subprocess.run(
                ["git", "-C", str(source_path), "pull", "--ff-only", "--quiet"],
                check=True,
                env=env,
            )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    _copy_published_tools(tool_dir, source_path / subdir)


def _refresh_tool_dir(tool_dir: Path) -> bool:
    source = tool_dir / ".centaur-source"
    metadata_path = tool_dir / ".centaur-tools-source.json"
    if not metadata_path.is_file():
        return False

    metadata = json.loads(metadata_path.read_text())
    sources = metadata.get("sources")
    if isinstance(sources, list) and sources:
        _clear_published_tools(tool_dir)
        for source_metadata in sources:
            if not isinstance(source_metadata, dict):
                raise RuntimeError(f"invalid tools source metadata in {metadata_path}: {source_metadata!r}")
            _refresh_source(tool_dir, source_metadata)
        return True

    subdir = metadata.get("source_subdir") or "tools"
    if metadata.get("source") == "repo_cache":
        repo_cache_repo_path = metadata.get("repo_cache_repo_path")
        if not repo_cache_repo_path:
            raise RuntimeError(f"repo-cache tools metadata is missing repo_cache_repo_path: {metadata_path}")
        _publish_tools(tool_dir, Path(repo_cache_repo_path) / subdir)
        return True

    if not source.is_dir():
        return False

    git_ref = metadata.get("git_ref")
    env, temp_dir = _git_env()
    try:
        if git_ref:
            subprocess.run(
                ["git", "-C", str(source), "-c", "gc.auto=0", "fetch", "--quiet", "origin", str(git_ref)],
                check=True,
                env=env,
            )
            subprocess.run(
                ["git", "-C", str(source), "checkout", "--quiet", "--detach", "FETCH_HEAD"],
                check=True,
                env=env,
            )
        else:
            subprocess.run(
                ["git", "-C", str(source), "pull", "--ff-only", "--quiet"],
                check=True,
                env=env,
            )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    _publish_tools(tool_dir, source / subdir)
    return True


def _refresh_tool_dirs(tool_dirs: list[Path]) -> int:
    refreshed = 0
    for tool_dir in tool_dirs:
        if _refresh_tool_dir(tool_dir):
            refreshed += 1
    return refreshed


# ---------------------------------------------------------------------------
# Best-effort client API extraction (AST only — no imports, no tool deps)
# ---------------------------------------------------------------------------

_SKIP_DECORATORS = {"property", "cached_property", "staticmethod", "classmethod", "overload"}


def _decorator_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for deco in fn.decorator_list:
        node = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _method_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = fn.args
    posonly = list(args.posonlyargs)
    normal = list(args.args)
    if posonly and posonly[0].arg in ("self", "cls"):
        posonly = posonly[1:]
    elif normal and normal[0].arg in ("self", "cls"):
        normal = normal[1:]
    stripped = ast.arguments(
        posonlyargs=posonly,
        args=normal,
        vararg=args.vararg,
        kwonlyargs=args.kwonlyargs,
        kw_defaults=args.kw_defaults,
        kwarg=args.kwarg,
        defaults=args.defaults,
    )
    try:
        rendered = ast.unparse(stripped)
    except Exception:  # noqa: BLE001 — stub rendering is best-effort
        rendered = "..."
    signature = f"{fn.name}({rendered})"
    if fn.returns is not None:
        try:
            signature += f" -> {ast.unparse(fn.returns)}"
        except Exception:  # noqa: BLE001
            pass
    return signature


def _extract_api(project_dir: Path, client_module: str) -> list[dict[str, str]]:
    """Extract public method stubs from a tool's client module without importing it."""
    path = project_dir / client_module
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError) as exc:
        print(f"warning: failed to parse {path}: {exc}", file=sys.stderr)
        return []

    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    target: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_client":
            if isinstance(node.returns, ast.Name) and node.returns.id in classes:
                target = classes[node.returns.id]
                break
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                    func = stmt.value.func
                    if isinstance(func, ast.Name) and func.id in classes:
                        target = classes[func.id]
                        break
            if target:
                break

    api: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if fn.name.startswith("_") or fn.name in seen:
            return
        if _decorator_names(fn) & _SKIP_DECORATORS:
            return
        seen.add(fn.name)
        entry = {"signature": _method_signature(fn)}
        doc = (ast.get_docstring(fn) or "").strip()
        if doc:
            entry["doc"] = doc.splitlines()[0]
        api.append(entry)

    def _add_class(cls: ast.ClassDef, visited: set[str]) -> None:
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _add(node)
        for base in cls.bases:
            if isinstance(base, ast.Name) and base.id in classes and base.id not in visited:
                visited.add(base.id)
                _add_class(classes[base.id], visited)

    if target is not None:
        _add_class(target, {target.name})
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add(node)
    return api


def _discover(
    tool_dirs: list[Path],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, object]]]:
    """Scan tool dirs for shim scripts and callable tool projects."""
    scripts: dict[str, dict[str, str]] = {}
    projects: dict[str, dict[str, object]] = {}
    for tool_dir in tool_dirs:
        if not tool_dir.is_dir():
            continue
        for pyproject in sorted(tool_dir.rglob("pyproject.toml")):
            if any(
                part in {".centaur-source", ".git", ".venv", "__pycache__"}
                for part in pyproject.parts
            ):
                continue
            try:
                data = tomllib.loads(pyproject.read_text())
            except (OSError, tomllib.TOMLDecodeError) as exc:
                print(f"warning: failed to read {pyproject}: {exc}", file=sys.stderr)
                continue
            project = data.get("project") or {}
            centaur_meta = (data.get("tool") or {}).get("centaur")
            project_scripts = project.get("scripts") or {}
            if not isinstance(project_scripts, dict):
                project_scripts = {}
            if centaur_meta is None and not project_scripts:
                continue
            client_module = str((centaur_meta or {}).get("module") or "client.py")
            package = str(project.get("name") or pyproject.parent.name)
            for name in sorted(project_scripts):
                if "/" in name or "\0" in name:
                    print(f"warning: ignoring invalid script name {name!r}", file=sys.stderr)
                    continue
                scripts[name] = {
                    "name": name,
                    "project_dir": str(pyproject.parent),
                    "package": package,
                    "entrypoint": str(project_scripts[name]),
                    "client_module": client_module,
                }
            dependencies = project.get("dependencies") or []
            if not isinstance(dependencies, list):
                dependencies = []
            projects[package] = {
                "name": package,
                "project_dir": str(pyproject.parent),
                "description": str(project.get("description") or ""),
                "client_module": client_module,
                "scripts": sorted(project_scripts),
                "dependencies": [str(dep) for dep in dependencies],
                "api": _extract_api(pyproject.parent, client_module),
            }
    return scripts, projects


# Union environment shared by in-process Code Mode dispatch. One venv holding
# the union of every tool's dependencies lets the `centaur_tools` proxy import
# client modules directly instead of paying a subprocess + uvx env per call.
_SDK_REQUIREMENTS = ["rich>=13.0"]  # centaur_sdk runtime deps (see centaur_sdk/pyproject.toml)


def _requirement_name(requirement: str) -> str:
    name = requirement.strip()
    for sep in " <>=!~[;(":
        name = name.split(sep, 1)[0]
    return name.lower().replace("_", "-")


def _ensure_union_env(projects: dict[str, dict[str, object]], env_dir: Path) -> bool:
    # Local packages (the SDK and the tool projects themselves) resolve via
    # PYTHONPATH, not PyPI — exclude them from the union requirements.
    local_names = {str(name).lower().replace("_", "-") for name in projects} | {"centaur-sdk"}
    requirements = sorted(
        {
            str(dep)
            for project in projects.values()
            for dep in (project.get("dependencies") or [])
            if _requirement_name(str(dep)) not in local_names
        }
        | set(_SDK_REQUIREMENTS)
    )
    requirements_text = "\n".join(requirements) + "\n"
    digest = hashlib.sha256(requirements_text.encode()).hexdigest()
    marker = env_dir / ".requirements.sha256"
    python = env_dir / "bin" / "python"
    if python.exists() and marker.is_file() and marker.read_text().strip() == digest:
        return True

    env_dir.mkdir(parents=True, exist_ok=True)
    try:
        if not python.exists():
            subprocess.run(
                ["uv", "venv", "--quiet", str(env_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
        requirements_path = env_dir / "requirements.txt"
        requirements_path.write_text(requirements_text)
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--python",
                str(python),
                "-r",
                str(requirements_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or "").strip()[-2000:]
        print(
            f"warning: failed to build Code Mode union env at {env_dir}: {exc}\n{detail}",
            file=sys.stderr,
        )
        return False
    marker.write_text(digest + "\n")
    print(
        f"Code Mode union env ready at {env_dir} ({len(requirements)} requirements)",
        file=sys.stderr,
    )
    return True


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_tool_shim(path: Path, script: dict[str, str], pythonpath: str) -> None:
    content = f"""#!/bin/sh
set -e
_centaur_tool_pythonpath={shlex.quote(pythonpath)}
if [ -n "$_centaur_tool_pythonpath" ]; then
  if [ -n "${{PYTHONPATH:-}}" ]; then
    export PYTHONPATH="$_centaur_tool_pythonpath:$PYTHONPATH"
  else
    export PYTHONPATH="$_centaur_tool_pythonpath"
  fi
fi
exec uvx --from {shlex.quote(script["project_dir"])} {shlex.quote(script["name"])} "$@"
"""
    _write_executable(path, content)


_CATALOG_TEMPLATE = '''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

INDEX = __INDEX_PATH__
PYTHONPATH_VALUE = __PYTHONPATH_VALUE__
LOG_FILE = os.environ.get(
    "CENTAUR_TOOL_LOG_FILE", str(Path.home() / ".local/state/centaur-tools/calls.jsonl")
)


def load():
    with open(INDEX) as f:
        data = json.load(f)
    if isinstance(data, list):  # legacy flat index of script entries
        return {"scripts": data, "projects": []}
    return data


def usage():
    print(
        "usage: centaur-tools [list|json|refresh|api [<name>]|which <name>|"
        "run <name> [args...]|call <name> <method> [json]]",
        file=sys.stderr,
    )
    return 2


CALL_RUNNER = r"""
import asyncio
import contextlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys

tool_name = sys.argv[1]
project_dir = Path(sys.argv[2])
client_module = sys.argv[3]
method = sys.argv[4]
payload = json.loads(sys.argv[5])

# Reserve real stdout for the JSON result; route incidental tool prints to stderr.
_real_stdout = sys.stdout
sys.stdout = sys.stderr
try:
    with contextlib.suppress(ImportError):
        from centaur_sdk.tool_sdk import ToolContext, set_tool_context

        set_tool_context(
            ToolContext(
                name=tool_name,
                thread_key=os.environ.get("CENTAUR_THREAD_KEY") or None,
                container_id=os.environ.get("HOSTNAME") or None,
            )
        )

    module_path = project_dir / client_module
    package_name = project_dir.name.replace("-", "_")
    if (project_dir / "__init__.py").is_file() and package_name.isidentifier() and module_path.suffix == ".py":
        parent = str(project_dir.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        module = importlib.import_module(f"{package_name}.{module_path.stem}")
    else:
        spec = importlib.util.spec_from_file_location("_centaur_tool_client", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load client module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    target = getattr(module, method, None)
    if target is None and hasattr(module, "_client"):
        target = getattr(module._client(), method, None)
    if target is None:
        raise RuntimeError(f"tool has no method {method}")

    if isinstance(payload, dict):
        result = target(**payload)
    elif payload is None:
        result = target()
    else:
        result = target(payload)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
finally:
    sys.stdout = _real_stdout
print(json.dumps(result, default=str, separators=(",", ":")))
"""


def _log_call(record):
    try:
        path = Path(LOG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {k: v for k, v in record.items() if v is not None}, separators=(",", ":")
        )
        with open(path, "a") as f:
            f.write(line + "\\n")
    except OSError:
        pass


def call_tool(tool, method, payload):
    project_dir = Path(tool["project_dir"])
    client_module = tool.get("client_module", "client.py")
    env = os.environ.copy()
    if PYTHONPATH_VALUE:
        if env.get("PYTHONPATH"):
            env["PYTHONPATH"] = f"{PYTHONPATH_VALUE}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = PYTHONPATH_VALUE
    payload_json = json.dumps(payload, separators=(",", ":"), default=str)
    started = time.monotonic()
    proc = subprocess.run(
        [
            "uvx",
            "--from",
            str(project_dir),
            "python",
            "-c",
            CALL_RUNNER,
            tool["name"],
            str(project_dir),
            client_module,
            method,
            payload_json,
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    _log_call(
        {
            "event": "tool_call",
            "ts": time.time(),
            "tool": tool["name"],
            "method": method,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "exit_code": proc.returncode,
            "arg_bytes": len(payload_json),
            "result_bytes": len(proc.stdout or ""),
            "thread_key": os.environ.get("CENTAUR_THREAD_KEY") or None,
        }
    )
    return proc


def print_api(project, verbose):
    import_name = project["name"].replace("-", "_")
    print(f"# {project['name']}: {project.get('description') or ''}".rstrip().rstrip(":"))
    if import_name.isidentifier():
        print(f"# python: from centaur_tools import {import_name}")
    else:
        print(f'# python: centaur_tools.tool("{project["name"]}")')
    scripts = project.get("scripts") or []
    if scripts:
        print(f"# cli: {', '.join(scripts)} (see <cli> --help)")
    api = project.get("api") or []
    if not api:
        print("# no client API extracted; use the CLI instead")
    for entry in api:
        print(entry["signature"])
        if verbose and entry.get("doc"):
            print(f"    # {entry['doc']}")


def main(argv):
    command = argv[1] if len(argv) > 1 else "list"
    if command == "refresh":
        return subprocess.call(["install-tool-shims", "--refresh"])
    data = load()
    projects_by_name = {project["name"]: project for project in data["projects"]}
    scripts_by_name = {script["name"]: script for script in data["scripts"]}
    callable_by_name = {**projects_by_name, **scripts_by_name}
    if command == "list":
        for name in sorted(projects_by_name):
            project = projects_by_name[name]
            description = project.get("description") or ""
            print(f"{name}\\t{description}")
        return 0
    if command == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    if command == "api":
        if len(argv) >= 3:
            name = argv[2]
            project = projects_by_name.get(name) or projects_by_name.get(
                name.replace("_", "-")
            )
            if not project and name in scripts_by_name:
                package = scripts_by_name[name].get("package")
                project = projects_by_name.get(package)
            if not project:
                print(f"unknown tool: {name}", file=sys.stderr)
                return 1
            print_api(project, verbose=True)
        else:
            for name in sorted(projects_by_name):
                project = projects_by_name[name]
                methods = len(project.get("api") or [])
                description = project.get("description") or ""
                print(f"{name}\\t{methods} methods\\t{description}")
        return 0
    if command == "which" and len(argv) == 3:
        tool = callable_by_name.get(argv[2])
        if not tool:
            print(f"unknown tool: {argv[2]}", file=sys.stderr)
            return 1
        print(tool["project_dir"])
        return 0
    if command == "run" and len(argv) >= 3:
        name = argv[2]
        if name not in scripts_by_name:
            print(f"unknown tool: {name}", file=sys.stderr)
            return 1
        return subprocess.call([name, *argv[3:]])
    if command == "call" and len(argv) >= 4:
        name = argv[2]
        method = argv[3]
        tool = callable_by_name.get(name) or callable_by_name.get(name.replace("_", "-"))
        if tool is None:
            print(f"unknown tool: {name}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(argv[4]) if len(argv) >= 5 else {}
            result = call_tool(tool, method, payload)
            if result.stdout:
                print(result.stdout, end="")
            if result.returncode != 0:
                if result.stderr:
                    print(result.stderr, file=sys.stderr, end="")
                return result.returncode
            return 0
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return usage()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
'''


def _write_catalog(path: Path, index_path: Path, pythonpath: str) -> None:
    content = _CATALOG_TEMPLATE.replace("__INDEX_PATH__", repr(str(index_path))).replace(
        "__PYTHONPATH_VALUE__", repr(pythonpath)
    )
    _write_executable(path, content)


_PROXY_TEMPLATE = '''"""Centaur Code Mode tool proxy (generated by install-tool-shims).

Compose deployment tools from Python instead of one shell call at a time:

    from centaur_tools import slack, linear

    messages = slack.search_messages(query="deploy failure", max_results=20)
    issues = linear.issues(team_key="INFRA", limit=20)
    # ... filter/join in code, print only the distilled result ...

Calls run in-process: the tool's client module is imported directly (its
dependencies live in a shared union env built at sandbox boot) and methods are
plain Python function calls. Secrets are still injected at the egress proxy.
If the union env cannot satisfy a tool's imports, the call transparently falls
back to `centaur-tools call` in an isolated per-tool env.

Calls are thread-safe: fan out with
`concurrent.futures.ThreadPoolExecutor(max_workers=8)`.

Discover tools with `centaur-tools api` and methods with
`centaur-tools api <tool>`. Hyphenated tool names: `tool("standard-metrics")`.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import threading
import time

INDEX = __INDEX_PATH__
CENTAUR_TOOLS_BIN = __CENTAUR_TOOLS_BIN__
ENV_DIR = __ENV_DIR__
PYTHONPATH_VALUE = __PYTHONPATH_VALUE__
LOG_FILE = os.environ.get(
    "CENTAUR_TOOL_LOG_FILE", str(Path.home() / ".local/state/centaur-tools/calls.jsonl")
)
_DEFAULT_TIMEOUT = float(os.environ.get("CENTAUR_TOOL_CALL_TIMEOUT", "600"))

_projects: dict[str, dict] | None = None
_modules: dict[str, object] = {}
_lock = threading.Lock()
_path_ready = False


def _load() -> dict[str, dict]:
    global _projects
    if _projects is None:
        with open(INDEX) as f:
            data = json.load(f)
        entries = data.get("projects", []) if isinstance(data, dict) else []
        _projects = {project["name"]: project for project in entries}
    return _projects


def _ensure_sys_path() -> None:
    """Add the union env site-packages and tool/SDK roots to sys.path once."""
    global _path_ready
    if _path_ready:
        return
    for part in PYTHONPATH_VALUE.split(os.pathsep):
        if part and os.path.isdir(part) and part not in sys.path:
            sys.path.append(part)
    env_ready = (Path(ENV_DIR) / ".requirements.sha256").is_file()
    if env_ready:
        for site_dir in sorted(Path(ENV_DIR).glob("lib/python*/site-packages")):
            site.addsitedir(str(site_dir))
    _path_ready = True


def _load_client_module(project: dict):
    """Import a tool's client module in-process (cached per project dir)."""
    import importlib
    import importlib.util

    project_dir = Path(project["project_dir"])
    cache_key = str(project_dir)
    with _lock:
        module = _modules.get(cache_key)
        if module is not None:
            return module
        _ensure_sys_path()
        module_path = project_dir / str(project.get("client_module") or "client.py")
        package_name = project_dir.name.replace("-", "_")
        if (
            (project_dir / "__init__.py").is_file()
            and package_name.isidentifier()
            and module_path.suffix == ".py"
        ):
            parent = str(project_dir.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            module = importlib.import_module(f"{package_name}.{module_path.stem}")
        else:
            unique = "_centaur_tool_" + "".join(
                ch if ch.isalnum() else "_" for ch in cache_key
            )
            spec = importlib.util.spec_from_file_location(unique, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load client module from {module_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        _modules[cache_key] = module
        return module


class ToolError(RuntimeError):
    """A tool call failed."""

    def __init__(self, tool: str, method: str, returncode: int, stderr: str):
        detail = (stderr or "").strip()[-2000:]
        super().__init__(f"{tool}.{method} failed (exit {returncode}): {detail}")
        self.tool = tool
        self.method = method
        self.returncode = returncode
        self.stderr = stderr


def _log_call(record: dict) -> None:
    try:
        path = Path(LOG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {k: v for k, v in record.items() if v is not None}, separators=(",", ":")
        )
        with open(path, "a") as f:
            f.write(line + "\\n")
    except OSError:
        pass


def _invoke_inproc(name: str, module, method: str, payload):
    target = getattr(module, method, None)
    if target is None and hasattr(module, "_client"):
        target = getattr(module._client(), method, None)
    if target is None:
        raise ToolError(name, method, 1, f"tool has no method {method}")

    token = None
    reset = None
    try:
        from centaur_sdk.tool_sdk import ToolContext, reset_tool_context, set_tool_context

        token = set_tool_context(
            ToolContext(
                name=name,
                thread_key=os.environ.get("CENTAUR_THREAD_KEY") or None,
                container_id=os.environ.get("HOSTNAME") or None,
            )
        )
        reset = reset_tool_context
    except ImportError:
        pass
    try:
        if isinstance(payload, dict):
            result = target(**payload)
        elif payload is None:
            result = target()
        else:
            result = target(payload)
        if inspect.isawaitable(result):
            import asyncio

            result = asyncio.run(result)
    finally:
        if reset is not None and token is not None:
            reset(token)
    # JSON round-trip so in-process results match the CLI dispatch path exactly.
    return json.loads(json.dumps(result, default=str))


def _invoke_cli(name: str, method: str, payload, timeout: float):
    proc = subprocess.run(
        [CENTAUR_TOOLS_BIN, "call", name, method, json.dumps(payload, default=str)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise ToolError(name, method, proc.returncode, proc.stderr or proc.stdout)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


class _Tool:
    def __init__(self, name: str):
        self._name = name

    def __repr__(self) -> str:
        return f"<centaur tool {self._name!r}>"

    def __getattr__(self, method: str):
        if method.startswith("_"):
            raise AttributeError(method)

        def _call(*args, _timeout: float = _DEFAULT_TIMEOUT, **kwargs):
            if args and kwargs:
                raise TypeError("pass either one positional payload or keyword arguments")
            if len(args) > 1:
                raise TypeError("at most one positional payload is allowed")
            payload = args[0] if args else kwargs

            module = None
            project = _load().get(self._name)
            if project is not None:
                try:
                    module = _load_client_module(project)
                except Exception:  # import failure -> isolated-env CLI fallback
                    module = None

            dispatch = "inproc" if module is not None else "cli"
            started = time.monotonic()
            ok = False
            try:
                if module is not None:
                    result = _invoke_inproc(self._name, module, method, payload)
                else:
                    result = _invoke_cli(self._name, method, payload, _timeout)
                ok = True
                return result
            finally:
                _log_call(
                    {
                        "event": "tool_call",
                        "ts": time.time(),
                        "tool": self._name,
                        "method": method,
                        "dispatch": dispatch,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "ok": ok,
                        "thread_key": os.environ.get("CENTAUR_THREAD_KEY") or None,
                    }
                )

        _call.__name__ = method
        _call.__qualname__ = f"{self._name}.{method}"
        return _call


def tool(name: str) -> _Tool:
    """Get a tool proxy by exact (possibly hyphenated) name."""
    return _Tool(name)


def tools() -> list[dict[str, str]]:
    """List available tools: [{"name", "description"}, ...]."""
    return [
        {"name": project["name"], "description": project.get("description") or ""}
        for project in _load().values()
    ]


def __getattr__(name: str) -> _Tool:
    for project_name in _load():
        if project_name.replace("-", "_") == name:
            return _Tool(project_name)
    raise AttributeError(
        f"no Centaur tool named {name!r}; run `centaur-tools api` to list tools"
    )


def __dir__():
    return sorted(
        {project.replace("-", "_") for project in _load()}
        | {"tool", "tools", "ToolError"}
    )
'''


def _write_proxy(
    proxy_dir: Path,
    index_path: Path,
    centaur_tools_bin: Path,
    env_dir: Path,
    pythonpath: str,
) -> None:
    package_dir = proxy_dir / "centaur_tools"
    package_dir.mkdir(parents=True, exist_ok=True)
    content = (
        _PROXY_TEMPLATE.replace("__INDEX_PATH__", repr(str(index_path)))
        .replace("__CENTAUR_TOOLS_BIN__", repr(str(centaur_tools_bin)))
        .replace("__ENV_DIR__", repr(str(env_dir)))
        .replace("__PYTHONPATH_VALUE__", repr(pythonpath))
    )
    (package_dir / "__init__.py").write_text(content)


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv[1:]
    env_only = "--env" in argv[1:]
    tool_dirs = _split_paths(os.environ.get("TOOL_DIRS", ""))
    bin_dir = Path(os.environ.get("CENTAUR_TOOL_BIN_DIR", str(Path.home() / ".local/bin")))
    env_dir = Path(
        os.environ.get(
            "CENTAUR_TOOL_ENV_DIR", str(Path.home() / ".local/share/centaur-tools/venv")
        )
    )
    bin_dir.mkdir(parents=True, exist_ok=True)

    if refresh:
        refreshed = _refresh_tool_dirs(tool_dirs)
        print(f"refreshed {refreshed} Centaur tool source dirs", file=sys.stderr)

    scripts, projects = _discover(tool_dirs)

    if env_only:
        return 0 if _ensure_union_env(projects, env_dir) else 1

    pythonpath_parts = [
        part for part in os.environ.get("CENTAUR_TOOL_PYTHONPATH", "").split(os.pathsep) if part
    ]
    sdk_parent = Path("/opt/centaur")
    if (sdk_parent / "centaur_sdk").is_dir() and str(sdk_parent) not in pythonpath_parts:
        pythonpath_parts.append(str(sdk_parent))
    pythonpath = os.pathsep.join(pythonpath_parts)

    for name, script in scripts.items():
        _write_tool_shim(bin_dir / name, script, pythonpath)

    index_path = bin_dir / ".centaur-tools.json"
    index_path.write_text(
        json.dumps(
            {"scripts": list(scripts.values()), "projects": list(projects.values())},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    _write_catalog(bin_dir / "centaur-tools", index_path, pythonpath)
    proxy_dir = Path(
        os.environ.get(
            "CENTAUR_TOOL_PROXY_DIR", str(Path.home() / ".local/share/centaur-tools/python")
        )
    )
    _write_proxy(proxy_dir, index_path, bin_dir / "centaur-tools", env_dir, pythonpath)
    # stdout is reserved for harness JSONL output (the session stdout pump streams
    # it to clients); write bootstrap notices to stderr so they never pollute it.
    print(
        f"installed {len(scripts)} Centaur tool CLI shims into {bin_dir}; "
        f"{len(projects)} tool projects exposed via centaur_tools at {proxy_dir}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
