"""Anchorage Digital API client with optional Ed25519 signing."""

import os
import time
from typing import Any

import httpx

BASE_URL = "https://api.anchorage.com/v2"

FUND_ENV_VARS = {
    "pf": ("ANCHORAGE_PF_API_KEY", "ANCHORAGE_PF_SIGNING_KEY"),
    "p1": ("ANCHORAGE_P1_API_KEY", "ANCHORAGE_P1_SIGNING_KEY"),
    "p2": ("ANCHORAGE_P2_API_KEY", "ANCHORAGE_P2_SIGNING_KEY"),
}

FUND_NAMES = {
    "pf": "Paradigm Fund",
    "p1": "Paradigm One",
    "p2": "Paradigm Two",
}


class AnchorageAuth(httpx.Auth):
    """Authentication for Anchorage API. Ed25519 signing is optional."""

    def __init__(self, access_key: str, signing_key_hex: str | None = None):
        self.access_key = access_key
        self.signing_key = None
        if signing_key_hex:
            from nacl.signing import SigningKey

            self.signing_key = SigningKey(bytes.fromhex(signing_key_hex))

    def auth_flow(self, request: httpx.Request):
        request.headers["Api-Access-Key"] = self.access_key

        if self.signing_key:
            timestamp = str(int(time.time()))
            method = request.method.upper()
            path_url = request.url.raw_path.decode("utf-8")
            body = request.content or b""

            message = timestamp.encode() + method.encode() + path_url.encode() + body
            signature = self.signing_key.sign(message).signature.hex()

            request.headers["Api-Signature"] = signature
            request.headers["Api-Timestamp"] = timestamp

        yield request


class AnchorageClient:
    """Client for Anchorage Digital API v2."""

    def __init__(self, fund: str = "pf", timeout: float = 30.0):
        self.fund = fund.lower()
        if self.fund not in FUND_ENV_VARS:
            raise ValueError(f"Invalid fund: {fund}. Must be one of: pf, p1, p2")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def fund_name(self) -> str:
        return FUND_NAMES.get(self.fund, self.fund.upper())

    def _get_auth(self) -> AnchorageAuth:
        api_key_var, signing_key_var = FUND_ENV_VARS[self.fund]
        api_key = os.getenv(api_key_var)
        signing_key = os.getenv(signing_key_var)  # Optional

        if not api_key:
            raise RuntimeError(
                f"{api_key_var} not set.\nSet the API key for {self.fund_name} to access Anchorage."
            )
        return AnchorageAuth(api_key, signing_key)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=BASE_URL,
                auth=self._get_auth(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def _request(
        self, method: str, path: str, params: dict | None = None, json: dict | None = None
    ) -> dict[str, Any] | list[Any]:
        response = self.client.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            try:
                error = response.json()
                msg = error.get("message", error.get("error", response.text))
            except Exception:
                msg = response.text
            raise RuntimeError(f"Anchorage API error ({response.status_code}): {msg}")
        return response.json()

    def list_vaults(self, limit: int = 25) -> list[dict]:
        """List all vaults."""
        data = self._request("GET", "/vaults", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    def get_vault(self, vault_id: str) -> dict:
        """Get vault details by ID."""
        data = self._request("GET", f"/vaults/{vault_id}")
        if isinstance(data, dict):
            return data.get("data", data)
        return data

    def get_balances(self) -> list[dict]:
        """Get all balances across vaults (derived from vault assets)."""
        vaults = self.list_vaults(limit=100)
        balances = []
        for vault in vaults:
            vault_name = vault.get("name", "")
            vault_id = vault.get("vaultId", "")
            for asset in vault.get("assets", []):
                total = asset.get("totalBalance", {})
                balances.append(
                    {
                        "asset": asset.get("assetType", ""),
                        "balance": total.get("quantity", "0"),
                        "usd_value": total.get("currentUSDValue", ""),
                        "vault_name": vault_name,
                        "vault_id": vault_id,
                        "wallet_id": asset.get("walletId", ""),
                    }
                )
        return balances

    def get_vault_balance(self, vault_id: str) -> list[dict]:
        """Get balance for a specific vault."""
        vault = self.get_vault(vault_id)
        balances = []
        for asset in vault.get("assets", []):
            total = asset.get("totalBalance", {})
            available = asset.get("availableBalance", {})
            balances.append(
                {
                    "asset": asset.get("assetType", ""),
                    "balance": total.get("quantity", "0"),
                    "available": available.get("quantity", "0"),
                    "usd_value": total.get("currentUSDValue", ""),
                }
            )
        return balances

    def list_transactions(self, limit: int = 50, vault_id: str | None = None) -> list[dict]:
        """List transfers."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        data = self._request("GET", "/transfers", params=params)
        if isinstance(data, dict):
            transfers = data.get("data", [])
        else:
            transfers = data
        if vault_id:
            transfers = [
                t
                for t in transfers
                if t.get("source", {}).get("id") == vault_id
                or t.get("destination", {}).get("id") == vault_id
            ]
        return transfers

    def get_addresses(self, vault_id: str) -> list[dict]:
        """Get deposit addresses for a vault."""
        data = self._request("GET", "/addresses", params={"vaultId": vault_id, "limit": 100})
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    def raw_request(self, method: str, endpoint: str, params: dict | None = None) -> dict | list:
        """Make a raw API call."""
        return self._request(method, endpoint, params=params)

    # Staking endpoints
    def list_staking_delegations(self, limit: int = 50) -> list[dict]:
        """List all staking delegations."""
        data = self._request("GET", "/staking/delegations", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    def get_staking_delegation(self, delegation_id: str) -> dict:
        """Get details of a specific staking delegation."""
        data = self._request("GET", f"/staking/delegations/{delegation_id}")
        if isinstance(data, dict):
            return data.get("data", data)
        return data

    def list_staking_rewards(self, limit: int = 50) -> list[dict]:
        """List staking rewards."""
        data = self._request("GET", "/staking/rewards", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    def get_staking_summary(self) -> dict:
        """Get staking summary across all assets."""
        data = self._request("GET", "/staking/summary")
        if isinstance(data, dict):
            return data.get("data", data)
        return data

    def list_validators(self, asset: str | None = None) -> list[dict]:
        """List available validators for staking."""
        params = {"limit": 100}
        if asset:
            params["assetType"] = asset
        data = self._request("GET", "/staking/validators", params=params)
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()



def _client(fund: str = "pf") -> AnchorageClient:
    return AnchorageClient(fund=fund)
