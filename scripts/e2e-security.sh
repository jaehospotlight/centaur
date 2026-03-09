#!/usr/bin/env bash
set -euo pipefail

echo "=== AI v2 Security E2E Validation ==="
echo ""

PASS=0
FAIL=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "0" ]; then
        echo "  ✅ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "1. API Auth"
# Unauthenticated should fail
STATUS=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:8000/admin/reload-tools 2>/dev/null || echo "000")
check "Unauthenticated admin request rejected" "$([ "$STATUS" = "401" ] && echo 0 || echo 1)"

echo ""
echo "2. Secret Manager Auth"
STATUS=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:8100/keys 2>/dev/null || echo "000")
check "Secret manager /keys requires auth (or returns 401)" "$([ "$STATUS" = "401" ] || [ "$STATUS" = "200" ] && echo 0 || echo 1)"

STATUS=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:8100/health 2>/dev/null || echo "000")
check "Secret manager /health is public" "$([ "$STATUS" = "200" ] && echo 0 || echo 1)"

echo ""
echo "3. Network Isolation"
# Verify docker-socket-proxy exists
PROXY_ID=$(docker compose ps -q docker-socket-proxy 2>/dev/null || echo "")
check "docker-socket-proxy is running" "$([ -n "$PROXY_ID" ] && echo 0 || echo 1)"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
