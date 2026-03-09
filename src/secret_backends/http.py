"""Backend that fetches secrets from the HTTP secret-manager sidecar."""

from __future__ import annotations

import logging
from threading import Lock
from time import monotonic
from urllib.parse import quote

from secret_backends.base import SecretBackend

log = logging.getLogger(__name__)


class HttpBackend(SecretBackend):
    """Fetch secrets from the secret-manager sidecar over HTTP.

    Results are cached locally for ``cache_ttl`` seconds to avoid repeated
    network calls.
    """

    def __init__(self, url: str, cache_ttl: float = 60.0, token: str = "") -> None:
        self._url = url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._token = token
        self._cache: dict[str, tuple[str, float]] = {}
        self._cache_lock = Lock()

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def get(self, key: str) -> str | None:
        now = monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                value, expiry = cached
                if now < expiry:
                    return value
                del self._cache[key]

        try:
            import httpx

            resp = httpx.get(
                f"{self._url}/secrets/{quote(key, safe='')}",
                headers=self._headers(),
                timeout=5.0,
            )
            if resp.status_code != 200:
                return None
            value = resp.json()["value"]
        except Exception:
            log.debug("secret-manager fetch failed for %s", key)
            return None

        with self._cache_lock:
            self._cache[key] = (value, monotonic() + self._cache_ttl)
        return value

    async def list_keys(self) -> list[str]:
        try:
            import httpx

            resp = httpx.get(f"{self._url}/keys", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json().get("keys", [])
        except Exception:
            log.debug("secret-manager list_keys failed")
        return []
