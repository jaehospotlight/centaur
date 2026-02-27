"""YouTube Data API client."""

import os
import subprocess

import httpx


class YouTubeClient:
    """Client for YouTube Data API v3."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _get_api_key(self) -> str | None:
        """Get API key from instance, env var, or 1Password."""
        if self._api_key:
            return self._api_key
        key = os.getenv("YOUTUBE_API_KEY")
        if key:
            return key
        try:
            result = subprocess.run(
                ["op", "read", "op://ai-agents/YouTube API Key/credential"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _request(
        self,
        endpoint: str,
        params: dict | None = None,
    ) -> dict:
        """Make an API request."""
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("YOUTUBE_API_KEY not set.")

        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        params["key"] = api_key

        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Request failed: {e}")

    def search(
        self,
        query: str,
        max_results: int = 10,
        type: str = "video",
        order: str = "relevance",
    ) -> dict:
        """Search for videos, channels, or playlists."""
        params = {
            "part": "snippet",
            "q": query,
            "maxResults": max_results,
            "type": type,
            "order": order,
        }
        return self._request("/search", params=params)

    def get_video(self, video_id: str) -> dict:
        """Get video details."""
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
        }
        return self._request("/videos", params=params)

    def get_channel(self, channel_id: str) -> dict:
        """Get channel details."""
        params = {
            "part": "snippet,statistics",
            "id": channel_id,
        }
        return self._request("/channels", params=params)

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _client() -> YouTubeClient:
    return YouTubeClient()
