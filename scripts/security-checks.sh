#!/usr/bin/env bash
# Static security checks — runs without Docker
set -euo pipefail

echo "=== Static Security Checks ==="
FAIL=0

# Check docker.sock not mounted on API
if grep -q 'docker.sock' docker-compose.yml | grep -v docker-socket-proxy | grep -v promtail; then
    echo "❌ docker.sock mounted on non-proxy service"
    FAIL=1
fi

# Check firewall has allowlist
if ! grep -q 'FIREWALL_SECRET_INJECTION_HOSTS' services/firewall/addon.py; then
    echo "❌ Firewall missing secret injection allowlist"
    FAIL=1
fi

# Check CIDR auth
if ! grep -q 'ipaddress' src/api/deps.py; then
    echo "❌ deps.py not using ipaddress module for CIDR trust"
    FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "✅ All static checks passed"
else
    echo "❌ Some checks failed"
    exit 1
fi
