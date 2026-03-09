"""Affinity API client."""

from typing import Any

import httpx
from shared.tool_sdk import secret

BASE_URL = "https://api.affinity.co"


class AffinityClient:
    """Client for Affinity CRM API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self.timeout = timeout
        self._client: httpx.Client | None = None

    def _get_api_key(self) -> str:
        api_key = self._api_key or secret("AFFINITY_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "AFFINITY_API_KEY not set.\n"
                "Generate one at https://affinity.co Settings > Integrations > API"
            )
        return api_key

    def _get_client(self) -> httpx.Client:
        """Get authenticated Affinity HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._get_api_key()}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any] | list[Any]:
        """Make authenticated request to Affinity API."""
        client = self._get_client()
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                error = response.json()
                msg = error.get("message", error.get("error", response.text))
            except Exception:
                msg = response.text
            raise RuntimeError(f"Affinity API error ({response.status_code}): {msg}")
        return response.json()

    def whoami(self) -> dict:
        """Get info about the current API token."""
        data = self._request("GET", "/whoami")
        return data

    def list_lists(self) -> list[dict]:
        """List all lists."""
        data = self._request("GET", "/lists")
        return data if isinstance(data, list) else []

    def get_list(self, list_id: int) -> dict:
        """Get list by ID."""
        data = self._request("GET", f"/lists/{list_id}")
        return data if isinstance(data, dict) else {}

    def get_list_entries(
        self,
        list_id: int,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict:
        """Get entries in a list."""
        params: dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        data = self._request("GET", f"/lists/{list_id}/list-entries", params=params)
        return data if isinstance(data, dict) else {"list_entries": []}

    def search_persons(
        self,
        term: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict:
        """Search for persons."""
        params: dict[str, Any] = {"page_size": page_size}
        if term:
            params["term"] = term
        if page_token:
            params["page_token"] = page_token
        data = self._request("GET", "/persons", params=params)
        return data if isinstance(data, dict) else {"persons": []}

    def get_person(self, person_id: int, with_interaction_dates: bool = False) -> dict:
        """Get person by ID."""
        params = {}
        if with_interaction_dates:
            params["with_interaction_dates"] = "true"
        data = self._request("GET", f"/persons/{person_id}", params=params)
        return data if isinstance(data, dict) else {}

    def search_organizations(
        self,
        term: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict:
        """Search for organizations."""
        params: dict[str, Any] = {"page_size": page_size}
        if term:
            params["term"] = term
        if page_token:
            params["page_token"] = page_token
        data = self._request("GET", "/organizations", params=params)
        return data if isinstance(data, dict) else {"organizations": []}

    def get_organization(self, org_id: int, with_interaction_dates: bool = False) -> dict:
        """Get organization by ID."""
        params = {}
        if with_interaction_dates:
            params["with_interaction_dates"] = "true"
        data = self._request("GET", f"/organizations/{org_id}", params=params)
        return data if isinstance(data, dict) else {}

    def raw_request(self, method: str, endpoint: str, data: dict | None = None) -> Any:
        """Make a raw API request."""
        kwargs = {}
        if data:
            kwargs["json"] = data
        return self._request(method, endpoint, **kwargs)

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _client() -> AffinityClient:
    api_key = secret("AFFINITY_API_KEY", "")
    if not api_key:
        raise RuntimeError("AFFINITY_API_KEY not set.")
    return AffinityClient(api_key=api_key)
