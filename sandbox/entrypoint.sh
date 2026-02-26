#!/bin/bash
set -e

HOME_DIR="$(eval echo ~)"
MCP_URL="${AI_V2_API_URL:-http://localhost:8000}/mcp/"
MCP_KEY="${AI_V2_API_KEY:-}"

# ── Write MCP configs directly (no template files needed) ────────────────────
if [ -n "$MCP_KEY" ]; then
    cat > "$HOME_DIR/.config/amp/settings.json" <<EOF
{"amp.experimental.compaction":95,"amp.mcpServers":{"tempo-ai":{"url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF
    cat > "$HOME_DIR/.claude.json" <<EOF
{"mcpServers":{"tempo-ai":{"type":"http","url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF
    cat > "$HOME_DIR/.codex/config.toml" <<EOF
model_auto_compact_token_limit = 120000
[mcp_servers.tempo-ai]
url = "${MCP_URL}"
EOF
fi

# ── Writable worktree ────────────────────────────────────────────────────────
if [ -n "${AGENT_REPO:-}" ] && [ -d "$HOME_DIR/github/$AGENT_REPO/.git" ]; then
    BRANCH="agent-$(date +%s)"
    git -C "$HOME_DIR/github/$AGENT_REPO" worktree add "$HOME_DIR/workspace" -b "$BRANCH" HEAD --quiet
fi
[ -f "$HOME_DIR/AGENTS.md" ] && [ -d "$HOME_DIR/workspace" ] && cp "$HOME_DIR/AGENTS.md" "$HOME_DIR/workspace/AGENTS.md" 2>/dev/null || true

# Signal readiness
touch "$HOME_DIR/.ready"

# ── Background: slow auth tasks ─────────────────────────────────────────────
{
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        git config --global credential.helper store
        printf 'https://oauth2:%s@github.com\n' "$GITHUB_TOKEN" > "$HOME_DIR/.git-credentials"
        echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
        gh auth setup-git 2>/dev/null || true
    fi
    CODEX_KEY="${CODEX_API_KEY:-${OPENAI_API_KEY:-}}"
    if [ -n "$CODEX_KEY" ]; then
        echo "$CODEX_KEY" | codex login --with-api-key 2>/dev/null || true
    fi
} &

exec "$@"
