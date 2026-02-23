# Tempo AI v2

A rebuild of the Tempo AI system with Postgres+pgvector for data, FastAPI+MCP for the API layer, and Codex+Docker for sandboxed code execution.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Tempo AI v2                        │
├──────────────┬──────────────────┬───────────────────────┤
│  dataplane/  │      api/        │     sandbox/          │
│              │                  │                       │
│  ETL from:   │  FastAPI server  │  Docker context with  │
│  - Slack     │  + MCP protocol  │  preloaded repos and  │
│  - Linear    │                  │  Codex runtime        │
│  - GitHub    │  Endpoints:      │                       │
│  - GCal      │  /query (SQL)    │  Provides isolated    │
│  - GDrive    │  /search (vec)   │  execution for agent  │
│  - Granola   │  /context        │  code changes         │
│  - Attio     │  /mcp/*          │                       │
│  - Pylon     │                  │                       │
│              │                  │                       │
│  ┌────────┐  │                  │                       │
│  │Postgres│  │                  │                       │
│  │pgvector│◄─┤                  │                       │
│  └────────┘  │                  │                       │
└──────────────┴──────────────────┴───────────────────────┘
```

### Data Plane (`dataplane/`)

ETL pipeline that ingests data from all Tempo sources into Postgres with pgvector embeddings:

- **Sources**: Slack, Linear, GitHub, Google Calendar, Google Drive, Granola, Attio, Pylon, BetterStack
- **Storage**: Postgres 16 with pgvector extension for semantic search
- **Embeddings**: OpenAI `text-embedding-3-small` via async batch processing
- **Scheduling**: Incremental sync with cursor-based pagination

Replaces the existing metronome SQLite+QMD system with a proper relational store and vector search.

### API Layer (`api/`)

FastAPI server exposing both REST and MCP (Model Context Protocol) endpoints:

- **`/query`** — Execute SQL queries against the data plane
- **`/search`** — Semantic vector search across all sources
- **`/context`** — Build context windows for agent prompts
- **`/mcp/*`** — MCP-compliant tool server for agent integration
- **Auth**: API key via `Authorization: Bearer <key>` header

### Sandbox (`sandbox/`)

Docker-based execution environment for Codex agent tasks:

- Pre-cloned Tempo repositories (configurable via `GITHUB_REPOS`)
- Toolchains: Rust, Python/uv, Node/pnpm, Go, Solidity/Foundry
- Network-isolated execution with controlled egress
- Ephemeral containers — destroyed after each task

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose
- Postgres 16 with pgvector (or use the included docker-compose)

### Setup

```bash
# Clone
gh repo clone tempoxyz/ai_v2 /repos/tempoxyz/ai_v2
cd /repos/tempoxyz/ai_v2

# Copy env and fill in secrets
cp .env.example .env

# Start Postgres
docker compose up -d

# Install Python deps
make install

# Run migrations
make migrate

# Run initial ETL sync
make sync

# Start API server
make api
```

### Development

```bash
make lint       # Ruff check + format
make test       # Run all tests
make migrate    # Apply Postgres migrations
```

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string |
| `OPENAI_API_KEY` | OpenAI API key for embeddings |
| `SLACK_TOKEN` | Slack Bot OAuth token |
| `LINEAR_API_KEY` | Linear API key |
| `GITHUB_TOKEN` | GitHub PAT |
| `API_SECRET_KEY` | Secret key for API auth |
| `SANDBOX_IMAGE` | Docker image for Codex sandbox |
| `GITHUB_REPOS` | Comma-separated repos to clone into sandbox |

## Deployment

Deployed to `dev-aibot` via systemd:

```bash
ssh ubuntu@dev-aibot
cd /repos/tempoxyz/ai_v2

# Update
git pull
make install
make migrate

# Restart services
sudo systemctl restart tempo-ai-v2-api
sudo systemctl restart tempo-ai-v2-sync
```

## Migration from Metronome

The dataplane includes a migration script to import existing metronome SQLite data:

```bash
# Export from metronome SQLite
python -m dataplane.migrate.from_metronome \
  --sqlite-path /path/to/metronome.db \
  --database-url postgresql://tempo:tempo_dev@localhost:5432/ai_v2
```

This imports all historical data and regenerates embeddings using pgvector.

## Project Structure

```
ai_v2/
├── dataplane/          # ETL pipeline + DB models
│   ├── src/
│   │   └── dataplane/
│   │       ├── sources/    # Per-source ETL (slack, linear, github, ...)
│   │       ├── models/     # SQLAlchemy models
│   │       ├── embeddings/ # Embedding generation
│   │       └── migrate/    # Migration from metronome
│   └── pyproject.toml
├── api/                # FastAPI + MCP server
│   ├── src/
│   │   └── api/
│   │       ├── routes/     # REST endpoints
│   │       ├── mcp/        # MCP protocol handlers
│   │       └── auth/       # API key auth
│   └── pyproject.toml
├── sandbox/            # Docker sandbox builder
│   ├── Dockerfile
│   ├── scripts/
│   └── pyproject.toml
├── migrations/         # Alembic migrations
├── scripts/            # Deployment + ops scripts
├── docker-compose.yml  # Local dev stack
├── pyproject.toml      # Root workspace config
├── Makefile
└── AGENTS.md
```
