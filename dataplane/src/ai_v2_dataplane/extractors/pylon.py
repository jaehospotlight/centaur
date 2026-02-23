from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..cursors import CursorStore, track_max_timestamp
from .base import BaseExtractor, ExtractResult, make_record

log = structlog.get_logger()

PYLON_API = "https://api.usepylon.com"
PAGE_LIMIT = 100
BACKFILL_DAYS = 90
MAX_MESSAGES_PER_ISSUE = 200
CONCURRENCY = 5
MAX_WINDOW_DAYS = 30


class PylonExtractor(BaseExtractor):
    source = "pylon"

    def __init__(
        self,
        api_token: str,
        backfill_days: int = BACKFILL_DAYS,
        rate_limit_delay_ms: int = 1000,
        concurrency: int = CONCURRENCY,
    ) -> None:
        self._token = api_token
        self._backfill_days = backfill_days
        self._rate_limit_delay = rate_limit_delay_ms / 1000.0
        self._concurrency = concurrency

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        reraise=True,
    )
    async def _api(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = await client.get(
            f"{PYLON_API}{path}",
            params=params or {},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            log.warning("pylon_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def _paginate_all(
        self,
        client: httpx.AsyncClient,
        path: str,
        params_base: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {**(params_base or {}), "limit": PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor

            data = await self._api(client, path, params)
            items = data.get("data", [])
            all_items.extend(items)

            pagination = data.get("pagination", {}) or {}
            if pagination.get("has_next_page") and pagination.get("cursor"):
                cursor = pagination["cursor"]
                if self._rate_limit_delay > 0:
                    await asyncio.sleep(self._rate_limit_delay)
            else:
                break

        return all_items

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._api(client, "/me")
                me = data.get("data", {})
                log.info("pylon_preflight_ok", name=me.get("name"))
                return True
            except Exception as e:
                log.error("pylon_preflight_failed", error=str(e))
                return False

    async def extract(
        self, pool: asyncpg.Pool, cursors: CursorStore
    ) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # 1. Accounts
            accounts = await self._paginate_all(client, "/accounts")
            records = [
                make_record("pylon", "account", a.get("id", "unknown"), a)
                for a in accounts
            ]
            n = await self._write_records(pool, records)
            kinds["account"] = n
            total += n
            log.info("pylon_accounts", count=len(accounts), written=n)

            # 2. Contacts
            contacts = await self._paginate_all(client, "/contacts")
            records = [
                make_record("pylon", "contact", c.get("id", "unknown"), c)
                for c in contacts
            ]
            n = await self._write_records(pool, records)
            kinds["contact"] = n
            total += n
            log.info("pylon_contacts", count=len(contacts), written=n)

            # 3. Issues (windowed by time, incremental via cursor)
            now = datetime.now(timezone.utc)
            backfill_start = now - timedelta(days=self._backfill_days)

            cursor_val = await cursors.get(pool, "pylon", "issue")
            if cursor_val:
                overlap = CursorStore.apply_overlap(cursor_val)
                try:
                    cursor_dt = datetime.fromisoformat(
                        overlap.replace("Z", "+00:00")
                    )
                    if cursor_dt > backfill_start:
                        backfill_start = cursor_dt
                except ValueError:
                    pass

            windows = _build_time_windows(backfill_start, now)
            all_issues: list[dict[str, Any]] = []

            for window in windows:
                window_issues = await self._paginate_all(
                    client,
                    "/issues",
                    {"start_time": window["start"], "end_time": window["end"]},
                )
                all_issues.extend(window_issues)

            records = [
                make_record("pylon", "issue", i.get("id", "unknown"), i)
                for i in all_issues
            ]
            n = await self._write_records(pool, records)
            kinds["issue"] = n
            total += n
            log.info(
                "pylon_issues",
                count=len(all_issues),
                windows=len(windows),
                written=n,
            )

            # 4. Messages per issue (concurrent)
            sem = asyncio.Semaphore(self._concurrency)
            msg_count = 0

            async def fetch_issue_messages(issue: dict[str, Any]) -> int:
                async with sem:
                    issue_id = issue.get("id", "")
                    if not issue_id:
                        return 0

                    # Skip if already synced and issue not updated
                    issue_ts = issue.get("updated_at") or issue.get("created_at")
                    msg_cursor = await cursors.get(
                        pool, "pylon", "message", issue_id
                    )
                    if msg_cursor and issue_ts and issue_ts <= msg_cursor:
                        return 0

                    try:
                        data = await self._api(
                            client, f"/issues/{issue_id}/messages"
                        )
                        messages = data.get("data", [])[:MAX_MESSAGES_PER_ISSUE]

                        records = [
                            make_record(
                                "pylon",
                                "message",
                                m.get("id", "unknown"),
                                {**m, "_issue_id": issue_id},
                            )
                            for m in messages
                        ]
                        written = await self._write_records(pool, records)

                        if issue_ts:
                            await cursors.set(
                                pool, "pylon", "message", issue_ts, issue_id
                            )

                        if self._rate_limit_delay > 0:
                            await asyncio.sleep(self._rate_limit_delay)

                        return written
                    except Exception:
                        return 0

            tasks = [fetch_issue_messages(issue) for issue in all_issues]
            results = await asyncio.gather(*tasks)
            msg_count = sum(results)
            kinds["message"] = msg_count
            total += msg_count
            log.info("pylon_messages", count=msg_count)

            # Track max updated_at
            max_ts = track_max_timestamp(all_issues, "updated_at")
            if not max_ts:
                max_ts = track_max_timestamp(all_issues, "created_at")
            if max_ts:
                await cursors.set(pool, "pylon", "issue", max_ts)

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="pylon",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )


def _build_time_windows(
    start: datetime, end: datetime
) -> list[dict[str, str]]:
    windows: list[dict[str, str]] = []
    window_start = start
    while window_start < end:
        window_end = min(
            window_start + timedelta(days=MAX_WINDOW_DAYS), end
        )
        windows.append(
            {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            }
        )
        window_start = window_end
    return windows
