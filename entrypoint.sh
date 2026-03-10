#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# API container entrypoint — bootstrap secrets then exec the command.
#
# The secrets container shares this Dockerfile but overrides entrypoint in
# docker-compose.yml so it never runs this script.
# ---------------------------------------------------------------------------

source /app/scripts/bootstrap-secrets.sh

bootstrap_required_secrets DATABASE_URL API_SECRET_KEY SLACK_SIGNING_SECRET SLACKBOT_API_KEY

# Canonical env aliases
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
