"""Security policy tests — static analysis of docker-compose config and code."""

import json
import os
import subprocess


def _load_compose() -> dict:
    """Parse docker-compose.yml via `docker compose config`."""
    # Fall back to reading YAML directly if docker compose not available
    try:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: parse YAML directly
    import yaml
    compose_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yml")
    with open(compose_path) as f:
        return yaml.safe_load(f)


class TestComposeNetworkSecurity:
    def test_agent_net_is_internal(self):
        compose = _load_compose()
        networks = compose.get("networks", {})
        agent_net = networks.get("agent_net", {})
        assert agent_net.get("internal") is True, "agent_net must be internal"

    def test_secrets_net_is_internal(self):
        compose = _load_compose()
        networks = compose.get("networks", {})
        secrets_net = networks.get("secrets_net", {})
        assert secrets_net.get("internal") is True, "secrets_net must be internal"

    def test_api_no_docker_socket(self):
        """API service must NOT mount docker.sock directly."""
        compose = _load_compose()
        services = compose.get("services", {})
        api = services.get("api", {})
        volumes = api.get("volumes", [])
        for v in volumes:
            vol_str = v if isinstance(v, str) else v.get("source", "")
            assert "docker.sock" not in str(vol_str), \
                f"API must not mount docker.sock: {vol_str}"

    def test_docker_socket_proxy_exists(self):
        compose = _load_compose()
        services = compose.get("services", {})
        assert "docker-socket-proxy" in services, \
            "docker-socket-proxy service must exist"


class TestFirewallSecurity:
    def test_firewall_addon_has_allowlist(self):
        """Firewall must have a destination allowlist for secret injection."""
        addon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "services", "firewall", "addon.py"
        )
        with open(addon_path) as f:
            content = f.read()
        assert "FIREWALL_SECRET_INJECTION_HOSTS" in content, \
            "Firewall must define FIREWALL_SECRET_INJECTION_HOSTS"
        assert "api.openai.com" in content, \
            "Firewall allowlist must include api.openai.com"

    def test_firewall_blocks_private_ips(self):
        """Firewall addon must block RFC1918/metadata IPs."""
        addon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "services", "firewall", "addon.py"
        )
        with open(addon_path) as f:
            content = f.read()
        assert "169.254" in content, "Firewall must block metadata IPs"
        assert "ipaddress" in content or "is_private" in content, \
            "Firewall must use IP validation"


class TestAuthSecurity:
    def test_deps_uses_cidr(self):
        """Auth deps must use CIDR-based trust, not prefix matching."""
        deps_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src", "api", "deps.py"
        )
        with open(deps_path) as f:
            content = f.read()
        assert "ipaddress" in content, "deps.py must use ipaddress module"
        assert "ip_network" in content or "ip_address" in content, \
            "deps.py must use CIDR-based trust"

    def test_secret_manager_has_auth(self):
        """Secret manager must require authentication on sensitive endpoints."""
        sm_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src", "secret_manager", "app.py"
        )
        with open(sm_path) as f:
            content = f.read()
        assert "SECRET_MANAGER_TOKEN" in content, \
            "Secret manager must support token auth"
