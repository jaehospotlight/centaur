# Centaur — Developer Guide

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd centaur
brew install just
```

Centaur runs locally on Kubernetes through the Helm chart. Infra secrets are required as pre-created Kubernetes Secrets. For local development, `just bootstrap-secrets` creates them from your shell environment:

```bash
export OP_SERVICE_ACCOUNT_TOKEN=...
export OP_VAULT=...
export SLACK_BOT_TOKEN=...
export SLACK_SIGNING_SECRET=...
export SLACKBOT_API_KEY=...
```

Application-level LLM/tool secrets such as OpenAI and Anthropic tokens stay in 1Password and are resolved in-flight by iron-proxy.

### 2. Boot the stack

```bash
just up
```

### Database migrations

Migrations are sqlx migrations in `services/api-rs/crates/centaur-session-sqlx/migrations` — numbered `.sql` files embedded into the binary via `sqlx::migrate!`. The api-rs server applies them on startup when `RUN_MIGRATIONS` is set (the Helm chart sets it). To add a migration, create the next numbered file in that directory.

## Architecture

See the [architecture diagram in the README](README.md#architecture).

### End-to-End Request Flow

1. User mentions bot in Slack → webhook → slackbotv2 → api-rs
2. api-rs spawns/reuses a Kubernetes sandbox pod (`centaur-agent:latest`) for that thread
3. Executes harness (amp/claude-code/codex) through the sandbox backend
4. Harness calls tools via the `call` helper — the in-pod tools sidecar when `CENTAUR_TOOLS_URL` is set, otherwise `$CENTAUR_API_URL` (REST, NOT MCP)
5. LLM API calls route through the per-sandbox iron-proxy, which injects real credentials
6. Results stream as JSON events → posted to Slack

### Service Interface Contracts

Centaur is a modular service architecture. Each service communicates through well-defined interfaces. As long as you implement these interfaces, you can swap or extend any layer independently.

**Client → API** (session control plane):

Clients (slackbotv2, CLI, external integrations) talk to api-rs over REST. The route surface is defined in `services/api-rs/crates/centaur-api-server/src/routes.rs`:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/session/{thread_key}` | Create or get the session for a thread |
| `POST /api/session/{thread_key}/messages` | Append user messages |
| `POST /api/session/{thread_key}/execute` | Enqueue an execution |
| `GET /api/session/{thread_key}/events` | Stream/replay session events (SSE) |
| `POST /api/sandboxes/drain` | Drain sandboxes |
| `/api/workflows/...`, `/api/webhooks/{slug}` | Workflow runs, events, and inbound webhooks (see [Durable Workflows](#durable-workflows)) |

Postgres is the source of truth — sessions, messages, executions, and events live in the `sessions`, `session_messages`, `session_executions`, and `session_events` tables (`services/api-rs/crates/centaur-session-sqlx/migrations`).

**API → Sandbox:**

api-rs drives sandbox Pods through the active sandbox backend's attach stream; the session runtime (`services/api-rs/crates/centaur-session-runtime`) normalizes each harness's JSON event stream into terminal results and replayable session events.

**Sandbox → API** (REST over Kubernetes services):

Agents call tools via the `call` helper (`services/sandbox/call.sh`): `call <tool> <method> [json]`. Tool requests go to the in-pod tools sidecar when `CENTAUR_TOOLS_URL` is set, otherwise to `$CENTAUR_API_URL`. Auth is via `CENTAUR_API_KEY` injected when the sandbox Pod is created.

### Network Isolation

The Helm chart installs deny-by-default NetworkPolicies, then explicitly allows the service paths the stack needs: slackbotv2 to api-rs, api-rs to Postgres/Kubernetes, sandbox Pods to the API and their per-sandbox iron-proxy, DNS, and configured egress.

## Directory Structure

```
centaur/
├── services/
│   ├── api-rs/           # Rust control plane (standalone service)
│   │   └── crates/       # centaur-api-server, centaur-session-runtime,
│   │                     # centaur-session-sqlx (migrations), centaur-workflows,
│   │                     # centaur-sandbox-agent-k8s, centaur-perms, …
│   ├── workflow-python/  # workflow_host.py — Python host that runs workflows/*.py for api-rs
│   ├── iron-proxy/       # Egress proxy image — credential injection + allowlist
│   ├── sandbox/          # Agent container image (Ubuntu 24.04 + uv + gh + node + bun + amp)
│   └── slackbotv2/       # Bun/TypeScript Slack event listener
├── centaur_sdk/          # Standalone SDK (pip install centaur-sdk)
├── packages/             # Shared packages (api-client, harness-events, rendering)
├── tools/                # Open-source tool plugins (auto-discovered)
│   ├── alchemy/          # One directory per tool — each has client.py + pyproject.toml
│   ├── websearch/
│   ├── telegram/
│   └── …                 # 60+ tool plugins (crypto, research, productivity, infra, …)
├── workflows/            # Workflow definitions (auto-discovered via WORKFLOW_DIRS)
├── contrib/              # Helm chart, operational scripts, assets
└── Justfile              # Local Helm/Kubernetes workflow
```

## Terminology

- **Chat SDK** always refers to the [Vercel Chat SDK](https://github.com/vercel/chat) (`~/github/vercel/chat`). When you need to understand how the Chat SDK or `@chat-adapter/*` packages work, **always read the source at `~/github/vercel/chat`** — never dig through `node_modules`.

## Testing Before Pushing

**NEVER push changes without testing them locally first.** Testing means actually running the affected service and proving the change works end-to-end — not just linting or reasoning about it.

1. **Build the affected service:** `just build-one <service>`
2. **Bring it up:** `just deploy`
3. **Make a real request** that exercises the change and show the output
4. **Only then** commit and push

For tool changes: verify via the `call` helper (`call <tool> <method> '<json>'`) from inside a sandbox pod. For Dockerfile/infra changes: rebuild, redeploy, and verify the binary/service is present and functional. For proxy changes: test from inside a sandbox pod through iron-proxy.

## Local-First Testing — Never Touch the Deploy Box

**All testing and E2E validation MUST happen on the local Kubernetes stack** (`just up` on this machine).
The deploy box is **production**. Changes reach it via `git push` → GitHub Actions auto-deploy. The only reasons to SSH into it are:
- Checking logs (`kubectl logs`, VictoriaLogs queries) for debugging production issues
- Emergency manual intervention — **only when the user explicitly asks**

For E2E testing, always:
1. `just build-one <service>` locally
2. `just deploy` locally
3. Run curl commands against `localhost` through `kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl ...`
4. Verify results locally
5. Only then commit, push, and let CI/CD handle production

## Code Conventions

- Python 3.11+, `uv` for deps, `ruff` for lint/format (line-length=100)
- `services/slackbotv2` is TypeScript run with `bun`
- All imports at top of file, never inside functions
- Absolute imports only: `from centaur_sdk.X` (workflow files may use `from api.workflow_engine`, provided by the workflow host's compat shim)
- All secrets via env vars or secret manager, never hardcode
- `asyncpg` for Postgres, `pgvector` for embeddings
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Lint & Test

Each service has its own `pyproject.toml` and `ruff.toml`. From the repo root:

```bash
uv run ruff check .          # lint
uv run ruff format .         # auto-fix
uv run pytest                # tests
```

## Plugin System — Tools & Workflows

Centaur has two plugin types that are auto-discovered at startup — no core code changes required to extend the system.

### Tool Plugins

Tools live in directories listed in `tools.toml` (`plugin_dirs`). Each tool is a directory with `client.py` (class + `_client()` factory), `pyproject.toml`, and optional `cli.py`. Tools are auto-discovered and exposed as REST endpoints at `/tools/{name}/{method}`, which agents reach through the `call` helper.

- `client.py`: NO `load_dotenv()`. Secrets via `secret()` from `centaur_sdk.tool_sdk`.
- `cli.py`: YES `load_dotenv()` at top. Thin typer wrapper for standalone use.
- Methods starting with `_` are excluded from registration.
- Tool dependencies declared in `pyproject.toml` are installed at image build time.

Example:

```python
# tools/my-tool/client.py
import httpx

class MyToolClient:
    def search(self, query: str, limit: int = 10) -> dict:
        """Search for something."""
        resp = httpx.get(f"https://api.example.com/search?q={query}&limit={limit}")
        return resp.json()

def _client():
    return MyToolClient()
```

### Workflow Plugins

Workflows live in directories listed in the `WORKFLOW_DIRS` env var (colon-separated paths). Each workflow is a single Python file exporting `WORKFLOW_NAME`, an async `handler(params, ctx)`, and optionally an `Input` dataclass, `WEBHOOKS`, and `SCHEDULE`. See [Durable Workflows](#durable-workflows) for the programming model.

Workflows ship in the top-level `workflows/` directory and are executed by `services/workflow-python/workflow_host.py` on behalf of api-rs (`centaur-workflows`). Overlay repos add more workflows by extending `WORKFLOW_DIRS`.

### Ordered Overlays

Centaur supports a first-class ordered overlay model, so organizations can extend the base repo without forking or relying on filesystem overlayfs. A common deployment keeps the base repo and an external overlay checkout side by side:

```
your-deployment/
├── centaur/              # This repo
└── centaur-overlay/      # Org-specific tools, workflows, skills, personas, prompt overlay
```

The Helm chart supports ordered overlays by mounting an overlay image or prompt content at `/app/overlay/org`, including its `tools/`, `workflows/`, `.agents/skills/`, persona prompts, and `services/sandbox/SYSTEM_PROMPT.md` after the base repo content.

Later overlay entries win cleanly when names collide, so the base repo stays generic while deployments can layer in org-specific behavior from outside the checkout.

## Durable Workflows

Workflow orchestration lives in api-rs (`services/api-rs/crates/centaur-workflows`), backed by the durable Postgres task engine in the `absurd` schema (see migration `0007_absurd_workflows.sql` and `services/api-rs/rfcs/0003-python-workflow-host.md`). api-rs owns workflow runs, retries, cancellation, checkpoint state, webhook ingress, and schedule firing. Workflow *handlers* stay in Python: api-rs launches `services/workflow-python/workflow_host.py`, which imports the workflow file, runs `handler(input, ctx)`, and delegates durable context operations back to api-rs over newline-delimited JSON on stdin/stdout.

The handler function IS the workflow — steps are runtime-discovered via `ctx.step(name, fn)` calls, each step result is checkpointed, and replay returns cached results instead of re-executing. Dynamic branching, loops, and conditional logic work naturally because it is just Python.

### WorkflowContext API

Every handler receives `(params, ctx)` where `ctx: WorkflowContext` (defined in `workflow_host.py`; importable as `from api.workflow_engine import WorkflowContext` via the compat shim) provides:

| Primitive | Purpose |
|-----------|---------|
| `ctx.step(name, fn)` | Execute *fn* exactly once; return the checkpointed result on replay. |
| `ctx.agent_turn(text=…)` / `ctx.run_agent(text=…)` | Run a durable agent turn through api-rs. |
| `ctx.call_tool(tool, method, args)` | Call a tool plugin. |
| `ctx.post_to_slack(channel, text, …)` | Post a Slack message. |
| `ctx.log(event, **fields)` | Structured log forwarded to api-rs. |

### Writing a workflow

```python
# workflows/my_workflow.py
from dataclasses import dataclass
from typing import Any
from api.workflow_engine import WorkflowContext

WORKFLOW_NAME = "my_workflow"

@dataclass
class Input:
    message: str = "hello"

async def handler(inp: Input, ctx: WorkflowContext) -> dict[str, Any]:
    greeting = await ctx.step("gather", lambda: {"msg": inp.message})
    result = await ctx.run_agent(text=f"Summarize: {greeting['msg']}")
    return {"greeting": greeting, "agent_result": result}
```

Workflow files may also export `WEBHOOKS` (to receive `POST /api/webhooks/{slug}`) and `SCHEDULE` (restart-safe schedule firing); see the examples in `workflows/` such as `github_issue_triage.py` and `google_calendar_sync.py`.

### Workflow REST API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/workflows/runs` | Create a workflow run |
| `GET /api/workflows/runs` | List runs |
| `GET /api/workflows/runs/{run_id}` | Get run details |
| `POST /api/workflows/runs/{run_id}/cancel` | Cancel a run |
| `POST /api/workflows/events` | Deliver an external event |
| `ANY /api/webhooks/{slug}` | Trigger a webhook-registered workflow |

## Agent Sandbox

### Overview

1 conversation = 1 Kubernetes sandbox Pod. The API spawns Pods running harness CLIs (amp, claude-code, codex). Inside the Pod, the harness calls back to the API via `curl` over REST.

### How the System Prompt Works

The sandbox image bakes `services/sandbox/SYSTEM_PROMPT.md` into `~/AGENTS.md` at build time. On container startup, `entrypoint.sh` copies it into the workspace root as `workspace/AGENTS.md` — this is the file that AI harnesses (Amp, Claude Code, Codex) read as their system instructions.

The system prompt tells the agent:
- **Identity**: it's running inside a Kubernetes sandbox pod, calling back to the API for tool access
- **Tools**: three kinds — harness built-ins (Read, Bash, etc.), API tools via the `call` helper, and a headless browser
- **`call` helper** (`/usr/local/bin/call`): a bash wrapper around `curl` that provides a concise syntax for API tool calls. `call slack get_channel_history '{"channel":"general"}'` instead of a full curl command. Returns TOON format for token efficiency.
- **Slack messaging**: the agent's stdout IS the Slack reply — never call `send_message` on the active thread
- **Dashboard blocks**: fenced code blocks with `dashboard` language tag render structured tables, charts, and KPI cards in compatible Centaur clients
- **Rules**: never display secrets, show your work, lead with the answer

The `call` helper (`services/sandbox/call.sh`) handles routing:
- `call <tool> <method> [json]` → `POST /tools/<tool>/<method>`
- `call discover <tool>` → `GET /tools/<tool>`

Legacy `call search` / `call sql` shorthands were removed. Sandbox agents should call the concrete tool directly, for example `call websearch search '{"query":"..."}'` or another deployment-specific query method discovered via `call discover <tool>`.

### Persona System

The entrypoint supports persona overlays via `AGENT_PERSONA`. Persona prompts are discovered from the loaded tool directories (including overlays such as `~/centaur-overlay`) and appended after the base + org overlay system prompts at container startup.

### Sandbox Pod Config

- Runs under Kubernetes NetworkPolicies with API reachable through the in-cluster service URL
- Entrypoint injects `CENTAUR_API_URL` and `CENTAUR_API_KEY` env vars
- Stub API keys so harnesses init in API-key mode (not browser login)
- `HTTPS_PROXY` routes LLM calls through the egress proxy (iron-proxy)
- Resource limits: 4GB memory, 2 CPUs
- Image tagged `centaur-agent:latest`
- Labels identify Centaur-managed sandboxes and carry thread/harness metadata for discovery/recovery

### Credential Injection (iron-proxy)

Sandbox Pods never see real API keys. Each sandbox's outbound HTTPS is MITM'd by its dedicated iron-proxy sidecar, which substitutes real credentials in-flight based on the secret grants resolved for the session's principal (see [Secrets](#secrets) and [centaur-perms](#centaur-perms)).

### Session Persistence

- **`sessions`** table: one row per thread — session identity, sandbox, and state
- **`session_messages`** / **`session_executions`** / **`session_events`** tables: durable transcript, execution, and replayable event state
- Pods are still discoverable via Kubernetes labels even if DB state needs reconciliation

## Security Model

- **API auth**: slackbotv2 authenticates to api-rs with a bearer key (`SLACKBOT_API_KEY`); workflow webhook routes verify their configured per-webhook auth.
- **Slack**: HMAC-SHA256 signature verification on all webhooks
- **Public edge**: The Helm chart exposes public routes only when configured through Ingress, HTTPRoute, or service settings.
- **Sandbox isolation**: Pods get placeholder credentials only; real keys injected by iron-proxy in-flight
- **Filesystem**: Host repos mounted read-only by default; only working repo is read-write
- **Kubernetes API**: The api-rs sandbox-manager service account is scoped to the operations needed to manage sandbox Pods.

## Secrets

Tool credentials (e.g., `ANTHROPIC_API_KEY`, `AMP_API_KEY`) are never materialized inside sandboxes or the API service. Tools declare which keys they need in their `pyproject.toml` and call `secret("KEY")` to receive a placeholder. Outbound HTTPS traffic is MITM'd by iron-proxy, which substitutes the real credential based on the secret grants managed in iron-control. iron-proxy resolves `op://...` references directly against 1Password.

For local development, infra secrets are stored in Kubernetes Secrets created by `just bootstrap-secrets`; application secrets continue to come from 1Password.

### iron-control

[iron-control](https://github.com/ironsh/iron-control) is an optional Rails control plane for authenticated API access and encrypted secret storage. It is off by default; enable it with `--set ironControl.enabled=true` (or set `ironControl.enabled: true` in a values file). When enabled, it runs against a dedicated `iron_control_production` database on the bundled Postgres (a separate logical DB so its Rails `schema_migrations` table never collides with Centaur's own migrations table), created by an idempotent init container.

`just bootstrap-secrets` seeds the required keys into `centaur-infra-env`: the three ActiveRecord encryption keys, `SECRET_KEY_BASE`, and the initial admin password/API key are auto-generated (only when absent, never rotated in place). `IRON_CONTROL_DATABASE_URL` defaults to the bundled Postgres server with no database path (so Rails resolves each connection's database name from the image's `database.yml`); export it before running `just bootstrap-secrets` to point at an external server. Override the admin email with `IRON_CONTROL_INITIAL_USER_EMAIL` (default `admin@centaur.local`).

### centaur-perms

`centaur-perms` is the operator CLI for iron-control permissions: it controls which Slack principals (users and channels) and which roles hold which tool roles and secrets. It lives at `services/api-rs/crates/centaur-perms` and reuses iron-control's canonical mappings (`derive_principal`, `RoleSpec::tool`), so every principal and role `foreign_id` it writes matches exactly what `api-rs` registers at session start. It is the supported way to inspect and edit grants by hand; the API writes the same resources at runtime.

#### Concepts

- **Principal** — a Slack user or channel that an agent session runs as. `foreign_id`s are derived canonically: `slack-channel-<team>-<conv>` for a channel, `slack-user-<team>-<user>` for a DM. A channel's grants win when present; otherwise the session falls back to the requesting user's grants.
- **Role** — a named bundle of secret grants assignable to principals. Canonical roles: `infra` (shared infra secrets), `tools` (shared harness/tool secrets), and one `tool-<slug>` per tool (e.g. `tool-github`).
- **Secret** — a typed iron-control resource (static `ssr_`, OAuth token `ots_`, GCP auth `gas_`, Postgres DSN `pgs_`, HMAC signing `hms_`). iron-control never returns credential values, only the source each resolves from. Each `tool-<slug>` secret keeps a canonical `tool-<slug>-…` id so the same object is shared no matter which role grants it.
- **Grant** — binds a secret to a grantee (a principal or a role). `centaur-perms` resources carry the label `managed-by=centaur`.

A principal's *effective* access is the union of its directly granted secrets and the secrets carried by every role assigned to it.

#### Setup

The CLI talks to the iron-control admin API. Provide the connection via flags or env vars (iron-control must be enabled — see above):

```bash
export IRON_CONTROL_URL=http://localhost:3000        # admin API base URL
export IRON_CONTROL_API_KEY=iak_…                    # admin API key
export IRON_CONTROL_NAMESPACE=default                # optional, defaults to "default"
```

For `--tool` lookups, point the CLI at the same tool directories the API uses, via repeatable `--tools-dir` flags or the colon-separated `TOOL_DIRS` env var (explicit dirs first, then env; later dirs shadow earlier ones, matching the overlay order). Build and run from `services/api-rs`:

```bash
cd services/api-rs
cargo run -p centaur-perms -- <args>     # or: cargo build -p centaur-perms; ./target/debug/centaur-perms <args>
```

The `--tool` flag parses a tool's `pyproject.toml` `[tool.centaur]` secrets and registers them in iron-control before granting. How each secret's `secret_ref` resolves to a source is set by `--source-policy` (`env` default, `onepassword`, or `onepassword-connect`); the 1Password policies also require `--op-vault` (and accept `--op-ttl`, default `10m`).

#### Command surface

Commands are resource-first — `centaur-perms <noun> <verb>`:

| Command | What it does |
|---------|--------------|
| `principals list [--filter S] [--label k=v] [--managed]` | List principals. `--filter` is a case-insensitive substring on `foreign_id`/name; `--managed` is shorthand for `--label managed-by=centaur`. |
| `principals show <principal> [--slack-user U]` | Show a principal's roles (with each role's grants), direct grants, and effective replace-secret placeholders. |
| `principals grant <principal> [--tool N] [--role F] [--secret OID]` | Grant access. `--tool` registers the tool's `tool-<slug>` role + secrets then assigns it; `--role` assigns an existing role; `--secret` grants a secret OID directly. All repeatable; creates the principal if absent. |
| `principals revoke <principal> [--tool N] [--role F] [--secret OID] [--grant-id OID]` | Reverse of grant. `--tool`/`--role` unassign the role; `--secret` deletes the direct grant for that secret; `--grant-id` deletes a grant by its `grant_…` id. |
| `roles list / show <role>` | List roles, or show the secrets granted to one role. |
| `roles grant <role> [--secret OID] [--tool N [--secret-name NAME]]` | Grant secrets to a role by OID, or register+grant a tool's declared secrets. `--secret-name` (repeatable, requires `--tool`) selects specific declared secrets instead of all. |
| `roles revoke <role> --secret OID` | Revoke one or more secrets from a role (`--secret` required, repeatable). |
| `secrets list [--filter S] [--label k=v] [--managed]` | List secrets across every type, one row per secret. |
| `secrets show <secret>` | Show one secret's full config by OID or `foreign_id` (values are never shown — only the source). |
| `broker create --foreign-id F --token-endpoint URL --client-id ID [--client-secret S] [--refresh-token SEED] [--scope SC]…` | Create or update an iron-control broker credential. Values are passed literally; iron-control owns the OAuth refresh loop. Re-supplying `--refresh-token` re-bootstraps it. |
| `broker list / show <credential> / delete <credential>` | List broker credentials, show one (status/expiry; secret material is never returned), or delete one (by `bcr_` OID or `foreign_id`). |

A `<principal>` argument is treated as a Slack thread key when it contains `:` (e.g. `slack:T123:C456:1700000000.0001`) and run through `derive_principal` — pass `--slack-user` so a DM thread keys to the user. Any value without a `:` is used verbatim as a `foreign_id` (e.g. `slack-channel-t123-c456`) or an OID. Grant/revoke operations are idempotent: re-granting an assigned role or revoking a missing grant is a no-op, reported as such.

A tool's `brokered_token` secret registers the *consumer* side — a static secret that injects the access token from a `token_broker` source. The broker credential itself (the managed OAuth refresh loop) is provisioned out of band with `broker create`; the tool's `brokered_token` references it by `foreign_id` (its `credential`, defaulting to the secret `name`).

#### Common workflows

Give a channel access to a tool (registers the tool's role + secrets from its `pyproject.toml`, then assigns the role to the channel):

```bash
centaur-perms principals grant slack-channel-t123-c456 --tool github --tools-dir tools
```

Inspect what a principal can actually do (resolve a live thread key, then list roles, direct grants, and effective secrets):

```bash
centaur-perms principals show slack:T123:C456:1700000000.0001
```

Give an individual user a tool only in their DMs:

```bash
centaur-perms principals grant slack:D9999999:1700000000.0001 --slack-user U07ABC --tool github --tools-dir tools
```

Register a tool's secrets once on the shared `tools` role, then assign that role to many principals:

```bash
centaur-perms roles grant tools --tool github --tools-dir tools
centaur-perms principals grant slack-channel-t123-c456 --role tools
```

Register only a single named secret from a tool onto a role:

```bash
centaur-perms roles grant infra --tool slackbot --secret-name SLACK_BOT_TOKEN --tools-dir tools
```

Revoke a tool from a channel (unassigns the `tool-<slug>` role; shared secrets on other roles are untouched):

```bash
centaur-perms principals revoke slack-channel-t123-c456 --tool github
```

Provision a managed broker credential a `brokered_token` secret (or a harness fragment) references — e.g. the Codex/Claude Code access-token harnesses reference `openai-codex` / `anthropic-claude`:

```bash
centaur-perms broker create --foreign-id openai-codex \
  --token-endpoint https://auth.openai.com/oauth/token \
  --client-id "$OPENAI_CODEX_CLIENT_ID" --refresh-token "$OPENAI_CODEX_REFRESH_TOKEN"
```

Audit Centaur-managed secrets and inspect one:

```bash
centaur-perms secrets list --managed
centaur-perms secrets show tool-github-github_token
```

## Observability & Audit Logs

### Architecture

All services write structured JSON logs to **stdout**. Kubernetes captures pod logs, and optional observability deployments can forward them to VictoriaLogs. VictoriaMetrics receives metrics via push from the API service when enabled.

```
Service → stdout (JSON) → Kubernetes pod logs → optional log collector → VictoriaLogs/Grafana
```

This design keeps the local Helm stack minimal while preserving structured logs for collectors.

### Components

| Component | Role | Config |
|-----------|------|--------|
| **VictoriaLogs** | Optional log storage + query engine | External/overlay deployment |
| **VictoriaMetrics** | Optional metrics storage + query engine | Push-based when enabled |
| **Grafana** | Optional dashboards + log explorer | External/overlay deployment |

### Querying logs

Via Grafana: navigate to **Explore → VictoriaLogs** and use [LogsQL](https://docs.victoriametrics.com/victorialogs/logsql/).

Via CLI (from inside the Kubernetes network):

```bash
# All logs for a specific thread
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s "http://victorialogs:9428/select/logsql/query" \
  --data-urlencode "query=thread_key:C042WDDP89Y" --data-urlencode "limit=50"

# API errors in the last hour
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s "http://victorialogs:9428/select/logsql/query" \
  --data-urlencode "query=_stream:{service=\"api\"} AND level:error" --data-urlencode "limit=20"

# Egress proxy audit trail for a time range
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s "http://victorialogs:9428/select/logsql/query" \
  --data-urlencode "query=event:proxy_audit" \
  --data-urlencode "start=2026-03-10T00:00:00Z" --data-urlencode "end=2026-03-11T00:00:00Z"
```

### Audit logging

The egress proxy (**iron-proxy**) emits a structured audit event for every outbound request from sandbox containers. These are searchable via `event:proxy_audit` in VictoriaLogs.

### Logging contract

Services must write single-line JSON to stdout with these fields:

| Field | Required | Description |
|-------|----------|-------------|
| `timestamp` | Yes | ISO 8601 timestamp |
| `level` | Yes | `debug`, `info`, `warning`, `error` |
| `service` | Yes | Service name (e.g. `api`, `slackbot`) |
| `event` | Yes | Machine-readable event name |
| `msg` | No | Human-readable message |
| `thread_key` | No | Thread identifier (when applicable) |

> **Never log secret values, auth headers, or raw tokens.**

## E2E Testing (without Slack)

### 1. Bring up the stack

```bash
just up
```

### 2. Run a session against api-rs

The supported clients are `centaur-session-cli` (`services/api-rs/crates/centaur-session-cli` — create, execute, or attach to a session) or direct curl against the session endpoints:

```bash
THREAD_KEY=test-e2e-1

# Create or get the session for a thread
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s -X POST \
  "http://localhost:8080/api/session/${THREAD_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"harness_type":"amp"}'

# Append a user message
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s -X POST \
  "http://localhost:8080/api/session/${THREAD_KEY}/messages" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","parts":[{"type":"text","text":"Reply with exactly PONG and nothing else."}]}]}'

# Enqueue an execution
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s -X POST \
  "http://localhost:8080/api/session/${THREAD_KEY}/execute" \
  -H "Content-Type: application/json" \
  -d '{}'

# Stream/replay events (SSE); reconnect with after_event_id
kubectl exec -n centaur deploy/centaur-centaur-api-rs -- curl -s -N \
  "http://localhost:8080/api/session/${THREAD_KEY}/events?after_event_id=0"
```

### Debugging

```bash
kubectl get pods -n centaur -l centaur-agent=true
kubectl logs -n centaur deploy/centaur-centaur-api-rs --tail=200
```
