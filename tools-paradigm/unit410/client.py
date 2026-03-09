"""Unit 410 API client."""

from typing import Any

import httpx
from shared.tool_sdk import secret

BASE_URL = "https://balanceapi-pd-prod.app.unit410.com"


class Unit410Client:
    """Client for Unit 410 balance API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self.base_url = BASE_URL
        self.timeout = timeout
        self._client: httpx.Client | None = None

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        api_key = secret("UNIT410_API_KEY", "")
        if not api_key:
            raise RuntimeError("UNIT410_API_KEY not set.")
        return api_key

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "x-api-key": self._get_api_key(),
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any] | list[Any]:
        """Make authenticated request to Unit 410 API."""
        response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                error = response.json()
                msg = error.get("message", error.get("error", response.text))
            except Exception:
                msg = response.text
            raise RuntimeError(f"Unit 410 API error ({response.status_code}): {msg}")
        return response.json()

    def get_balances(self) -> list[dict]:
        """Get all wallet balances.

        Returns list of wallets with their balances across networks/strategies.
        Each wallet contains: address, account, network, strategy, timestamp, balances.
        """
        data = self._request("GET", "/balances")
        if isinstance(data, dict):
            return data.get("result", [])
        return data

    def list_wallets(self) -> list[dict]:
        """Alias for get_balances - list all wallets with balances."""
        return self.get_balances()

    def get_wallets_by_network(self, network: str) -> list[dict]:
        """Get wallets filtered by network (e.g., 'ethereum', 'hyperliquid')."""
        wallets = self.get_balances()
        return [w for w in wallets if w.get("network", "").lower() == network.lower()]

    def get_wallets_by_account(self, account: str) -> list[dict]:
        """Get wallets filtered by account (e.g., 'flp', 'onelp')."""
        wallets = self.get_balances()
        return [w for w in wallets if w.get("account", "").lower() == account.lower()]

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _client() -> Unit410Client:
    return Unit410Client()
