from __future__ import annotations

import os
from typing import Any

import httpx


class SendEmailClient:
    def __init__(self, api_url: str | None = None, api_key: str | None = None) -> None:
        self.api_url = (api_url or os.getenv("CENTAUR_API_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("CENTAUR_API_KEY") or ""

    async def send_email(
        self,
        *,
        trigger_message_ts: str,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            raise RuntimeError("CENTAUR_API_URL and CENTAUR_API_KEY are required")
        payload = {
            "thread_key": os.getenv("CENTAUR_THREAD_KEY", ""),
            "trigger_message_ts": trigger_message_ts,
            "to": to,
            "cc": cc or [],
            "bcc": bcc or [],
            "subject": subject,
            "body": body,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.api_url}/internal/gmail-oauth/send-email-tool",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        data = response.json()
        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            if detail in {"not_connected", "connection_invalid"}:
                raise RuntimeError("Gmail is not connected or is invalid. Ask the user to run /ai-email-connect.")
            raise RuntimeError(f"send_email confirmation staging failed: {detail or response.status_code}")
        return data
