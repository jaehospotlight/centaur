#!/usr/bin/env bash
set -euo pipefail

source /app/bootstrap-secrets.sh

bootstrap_required_secrets SLACKBOT_API_KEY DATABASE_URL

exec "$@"
