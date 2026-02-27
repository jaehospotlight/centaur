"""FalconX API client with HMAC authentication."""

import base64
import hashlib
import hmac
import os
import time
from typing import Literal

import httpx

BASE_URL = "https://api.falconx.io"

AccountType = Literal["p1", "pf"]


def get_credentials(account: AccountType = "p1") -> tuple[str, str, str]:
    """Get API credentials for the specified account.

    Args:
        account: Account type - 'p1' for Paradigm One, 'pf' for Paradigm Fund

    Returns:
        Tuple of (api_key, passphrase, secret_key)

    Raises:
        RuntimeError: If credentials are not set
    """
    prefix = f"FALCONX_{account.upper()}"
    api_key = os.getenv(f"{prefix}_API_KEY")
    passphrase = os.getenv(f"{prefix}_PASSPHRASE")
    secret_key = os.getenv(f"{prefix}_SECRET_KEY")

    if not all([api_key, passphrase, secret_key]):
        missing = []
        if not api_key:
            missing.append(f"{prefix}_API_KEY")
        if not passphrase:
            missing.append(f"{prefix}_PASSPHRASE")
        if not secret_key:
            missing.append(f"{prefix}_SECRET_KEY")
        raise RuntimeError(f"Missing FalconX credentials: {', '.join(missing)}")

    return api_key, passphrase, secret_key


def sign_request(
    secret_key: str,
    timestamp: str,
    method: str,
    path: str,
    body: str = "",
) -> str:
    """Generate HMAC-SHA256 signature for FalconX API request.

    Args:
        secret_key: Base64-encoded secret key
        timestamp: Unix timestamp as string
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g., /v1/balances)
        body: Request body (empty string for GET requests)

    Returns:
        Base64-encoded signature
    """
    message = timestamp + method.upper() + path + body
    secret_bytes = base64.b64decode(secret_key)
    signature = hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(signature.digest()).decode("utf-8")


class FalconXClient:
    """Client for FalconX API."""

    def __init__(self, account: AccountType = "p1", timeout: float = 30.0):
        """Initialize the FalconX client.

        Args:
            account: Account type - 'p1' or 'pf'
            timeout: Request timeout in seconds
        """
        self.account = account
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=BASE_URL, timeout=self.timeout)
        return self._client

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        """Make an authenticated API request.

        Args:
            method: HTTP method
            path: API endpoint path
            body: Optional request body for POST/PUT
            params: Optional query parameters

        Returns:
            JSON response data

        Raises:
            RuntimeError: If the request fails
        """
        api_key, passphrase, secret_key = get_credentials(self.account)
        timestamp = str(int(time.time()))
        body_str = ""
        if body:
            import json

            body_str = json.dumps(body)

        # For GET requests with params, include query string in signature path
        sign_path = path
        if params and method.upper() == "GET":
            from urllib.parse import urlencode

            sign_path = f"{path}?{urlencode(params)}"

        signature = sign_request(secret_key, timestamp, method, sign_path, body_str)

        headers = {
            "FX-ACCESS-KEY": api_key,
            "FX-ACCESS-SIGN": signature,
            "FX-ACCESS-TIMESTAMP": timestamp,
            "FX-ACCESS-PASSPHRASE": passphrase,
            "Content-Type": "application/json",
        }

        try:
            if method.upper() == "GET":
                response = self.client.get(path, headers=headers, params=params)
            elif method.upper() == "POST":
                response = self.client.post(path, headers=headers, content=body_str, params=params)
            else:
                response = self.client.request(
                    method, path, headers=headers, content=body_str, params=params
                )

            if response.status_code >= 400:
                try:
                    error = response.json()
                    msg = error.get("message", error.get("error", response.text))
                except Exception:
                    msg = response.text
                raise RuntimeError(f"FalconX API error ({response.status_code}): {msg}")

            return response.json()
        except httpx.RequestError as e:
            raise RuntimeError(f"Request failed: {e}")

    def get_quote(
        self,
        base: str,
        quote: str,
        quantity: float,
        side: str = "buy",
    ) -> dict:
        """Get a quote for a trade (v3 endpoint).

        Args:
            base: Base token (e.g., BTC)
            quote: Quote token (e.g., USD)
            quantity: Amount to trade
            side: 'buy' or 'sell'

        Returns:
            Quote details including price and fx_quote_id
        """
        body = {
            "token_pair": {"base_token": base.upper(), "quote_token": quote.upper()},
            "quantity": {"token": base.upper(), "value": str(quantity)},
            "side": side.lower(),
        }
        return self._request("POST", "/v3/quotes", body=body)

    def execute_quote(self, quote_id: str) -> dict:
        """Execute a previously obtained quote (v3 endpoint).

        Args:
            quote_id: The FalconX quote ID to execute

        Returns:
            Execution details
        """
        body = {"fx_quote_id": quote_id}
        return self._request("POST", "/v3/quotes/execute", body=body)

    def get_balances(self) -> dict:
        """Get account balances.

        Returns:
            Account balance information
        """
        return self._request("GET", "/v1/balances")

    def list_trades(self, days: int = 30) -> list:
        """List executed quotes (trade history).

        Args:
            days: Number of days of history to fetch (max 31)

        Returns:
            List of executed quotes/trades
        """
        from datetime import datetime, timedelta, timezone

        t_end = datetime.now(timezone.utc)
        t_start = t_end - timedelta(days=min(days, 31))
        params = {
            "t_start": t_start.isoformat(),
            "t_end": t_end.isoformat(),
        }
        result = self._request("GET", "/v1/quotes", params=params)
        if isinstance(result, list):
            return result
        return result.get("data", result.get("quotes", []))

    def get_trade(self, quote_id: str) -> dict:
        """Get status for a specific quote/trade.

        Args:
            quote_id: The FalconX quote ID

        Returns:
            Quote/trade details
        """
        return self._request("GET", f"/v1/quotes/{quote_id}")

    def list_pairs(self) -> list:
        """List available trading pairs.

        Returns:
            List of trading pairs
        """
        result = self._request("GET", "/v1/pairs")
        if isinstance(result, dict):
            return result.get("data", result.get("pairs", []))
        return result

    def raw_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        """Make a raw API request.

        Args:
            method: HTTP method
            path: API endpoint path
            body: Optional request body
            params: Optional query parameters

        Returns:
            JSON response data
        """
        return self._request(method, path, body=body, params=params)

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()



def _client(account: str = "p1") -> FalconXClient:
    return FalconXClient(account=account)
