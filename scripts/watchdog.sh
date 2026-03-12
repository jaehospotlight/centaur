#!/usr/bin/env bash
# Watchdog: checks API health and auto-recovers the stack.
# Installed as a systemd timer — runs every 2 minutes.
# If the API is unreachable for 3 consecutive checks, pulls latest and redeploys.
set -euo pipefail

DEPLOY_DIR="/home/ubuntu/github/paradigmxyz/centaur"
STATE_FILE="/tmp/centaur_watchdog_failures"
MAX_FAILURES=3

failures=$(cat "$STATE_FILE" 2>/dev/null || echo 0)

if curl -sf --max-time 10 http://localhost:8000/health > /dev/null 2>&1; then
    # Healthy — reset counter
    echo 0 > "$STATE_FILE"
    exit 0
fi

# Unhealthy
failures=$((failures + 1))
echo "$failures" > "$STATE_FILE"
echo "[watchdog] Health check failed ($failures/$MAX_FAILURES)"

if [ "$failures" -ge "$MAX_FAILURES" ]; then
    echo "[watchdog] Threshold reached — recovering stack"
    cd "$DEPLOY_DIR"
    git fetch origin main
    git checkout main
    git reset --hard origin/main
    docker compose up -d --build
    echo 0 > "$STATE_FILE"
    echo "[watchdog] Recovery complete"
fi
