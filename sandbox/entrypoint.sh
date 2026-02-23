#!/bin/bash
set -e

# Update repos if SYNC_ON_START is set
if [ "${SYNC_ON_START:-false}" = "true" ]; then
    echo "Syncing repositories..."
    for dir in /repos/tempoxyz/*/; do
        if [ -d "$dir/.git" ]; then
            repo=$(basename "$dir")
            echo "  Updating $repo..."
            cd "$dir" && git fetch origin && git reset --hard origin/HEAD 2>/dev/null || true
            cd /repos
        fi
    done
    echo "Repo sync complete."
fi

exec "$@"
