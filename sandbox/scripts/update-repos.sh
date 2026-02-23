#!/bin/bash
# Update all repos in /repos/tempoxyz/
# Run via cron: 0 */6 * * * /path/to/update-repos.sh

set -euo pipefail

REPOS_DIR="${REPOS_DIR:-/repos/tempoxyz}"
GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}"

# List of repos to sync
REPOS=(
    tempo ai ai_v2 metronome tempo-apps tempo-web app docs
    tempo-ts tempo-go tempo-foundry tempo-std ai-payments
    dev-infra prd-infra helm-charts ci mpp mpp-rs
    presto presto-rs agent-skills derek profiler-cli
    dev-portal tempo-stack chains lints
)

SYNCED=0
FAILED=0

for repo in "${REPOS[@]}"; do
    dir="$REPOS_DIR/$repo"
    if [ -d "$dir/.git" ]; then
        echo "Updating $repo..."
        if cd "$dir" && git fetch origin --depth=1 && git reset --hard origin/HEAD 2>/dev/null; then
            SYNCED=$((SYNCED + 1))
        else
            echo "  WARN: failed to update $repo"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "Cloning $repo..."
        if gh repo clone "tempoxyz/$repo" "$dir" -- --depth=1 2>/dev/null; then
            SYNCED=$((SYNCED + 1))
        else
            echo "  WARN: failed to clone $repo"
            FAILED=$((FAILED + 1))
        fi
    fi
done

echo "Done. Synced: $SYNCED, Failed: $FAILED. $(date)"
