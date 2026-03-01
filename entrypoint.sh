#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Container entrypoint.
#
# Secret management is handled by the dedicated `secrets` sidecar service
# (src/secret_manager/) which caches 1Password vault contents and serves
# them over HTTP.  No 1Password bootstrap is needed here.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Canonical env aliases
# Keep app code stable on canonical names while allowing legacy/box-specific
# variable names from .env or 1Password item titles.
# ---------------------------------------------------------------------------
if [[ -z "${SLACK_BOT_TOKEN:-}" && -n "${SLACK_TOKEN:-}" ]]; then
    export SLACK_BOT_TOKEN="${SLACK_TOKEN}"
fi
if [[ -z "${GITHUB_TOKEN:-}" && -n "${GH_TOKEN:-}" ]]; then
    export GITHUB_TOKEN="${GH_TOKEN}"
fi
if [[ -z "${GITHUB_TOKEN:-}" && -n "${GITHUB_PAT:-}" ]]; then
    export GITHUB_TOKEN="${GITHUB_PAT}"
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" && -n "${ANTHROPIC_KEY:-}" ]]; then
    export ANTHROPIC_API_KEY="${ANTHROPIC_KEY}"
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" && -n "${CLAUDE_API_KEY:-}" ]]; then
    export ANTHROPIC_API_KEY="${CLAUDE_API_KEY}"
fi

exec "$@"
