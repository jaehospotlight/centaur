"""Tardis API client."""

import os

import httpx


class TardisClient:
    """Client for Tardis.dev API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self.base_url = "https://api.tardis.dev/v1"
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _get_api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        return os.getenv("TARDIS_API_KEY")

    def _headers(self) -> dict[str, str]:
        api_key = self._get_api_key()
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return {}

    def _request(self, endpoint: str, params: dict | None = None) -> dict | list:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.client.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Request failed: {e}")

    def list_exchanges(self) -> list[dict]:
        """List all supported exchanges."""
        return self._request("/exchanges")

    def get_exchange(self, exchange: str) -> dict:
        """Get exchange details including available symbols and channels."""
        return self._request(f"/exchanges/{exchange}")

    def get_instruments(self, exchange: str, filter_obj: dict | None = None) -> list[dict]:
        """Get instruments for an exchange with optional filter."""
        params = {}
        if filter_obj:
            import json

            params["filter"] = json.dumps(filter_obj)
        return self._request(f"/instruments/{exchange}", params=params if params else None)

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _client() -> TardisClient:
    return TardisClient()
