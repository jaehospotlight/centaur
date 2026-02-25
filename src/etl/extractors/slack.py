from __future__ import annotations

import asyncio
import time
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

from etl.extractors.base import BaseExtractor, ExtractResult, make_record
from shared.cursors import CursorStore

log = structlog.get_logger()

SLACK_API = "https://slack.com/api"

# Rate limit tiers (ms between calls)
TIER3_DELAY = 1.05  # conversations.history, conversations.replies
TIER2_DELAY = 3.0  # conversations.list, users.list, pins.list, bookmarks.list, files.list

BACKFILL_DAYS = 90
THREAD_LOOKBACK_DAYS = 3


class RateLimitError(Exception):
    def __init__(self, retry_after: float = 30.0) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class SlackExtractor(BaseExtractor):
    source = "slack"

    def __init__(
        self,
        token: str,
        channels: list[str] | None = None,
        include_dms: bool = False,
        backfill_days: int = BACKFILL_DAYS,
    ) -> None:
        self._token = token
        self._channels = channels or []
        self._include_dms = include_dms
        self._backfill_days = backfill_days
        self._last_call: dict[str, float] = {}

    async def _throttle(self, method: str, delay: float) -> None:
        last = self._last_call.get(method, 0)
        elapsed = time.monotonic() - last
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_call[method] = time.monotonic()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, RateLimitError)),
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )
    async def _api(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = await client.get(
            f"{SLACK_API}/{method}",
            params=params or {},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "30"))
            log.warning("slack_rate_limited", method=method, retry_after=retry_after)
            await asyncio.sleep(retry_after)
            raise RateLimitError(retry_after)

        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            error = data.get("error", "unknown")
            if error in ("not_in_channel", "channel_not_found", "missing_scope"):
                log.info("slack_api_skip", method=method, error=error)
                return data
            raise httpx.HTTPStatusError(
                f"Slack API error: {error}",
                request=resp.request,
                response=resp,
            )
        return data

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._api(client, "auth.test")
                user = data.get("user", "unknown")
                team = data.get("team", "unknown")
                log.info("slack_preflight_ok", user=user, team=team)
                return True
            except Exception as e:
                log.error("slack_preflight_failed", error=str(e))
                return False

    async def extract(self, pool: asyncpg.Pool, cursors: CursorStore) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # 1. Channels
            channels = await self._fetch_all_channels(client)
            records = [
                make_record("slack", "channel", ch.get("id", "unknown"), ch) for ch in channels
            ]
            n = await self._write_records(pool, records)
            kinds["channel"] = n
            total += n
            log.info("slack_channels", count=len(channels), written=n)

            # 2. Users
            users = await self._fetch_all_users(client)
            records = [make_record("slack", "user", u.get("id", "unknown"), u) for u in users]
            n = await self._write_records(pool, records)
            kinds["user"] = n
            total += n
            log.info("slack_users", count=len(users), written=n)

            # 3. Messages (per channel, with thread replies)
            oldest = str(int(time.time()) - self._backfill_days * 86400)
            msg_targets = self._filter_message_targets(channels)

            for ch in msg_targets:
                ch_id = ch.get("id", "")
                ch_name = ch.get("name", ch_id)

                cursor_val = await cursors.get(pool, "slack", "history", ch_id)
                effective_oldest = cursor_val if cursor_val else oldest
                # Apply thread lookback overlap
                if cursor_val:
                    lookback = THREAD_LOOKBACK_DAYS * 86400
                    effective_oldest = str(max(float(cursor_val) - lookback, float(oldest)))

                ch_written, max_ts = await self._fetch_channel_messages(
                    client, pool, ch_id, effective_oldest, cursors
                )
                kinds["message"] = kinds.get("message", 0) + ch_written
                total += ch_written

                if max_ts:
                    await cursors.set(pool, "slack", "history", max_ts, ch_id)

                log.info(
                    "slack_channel_done",
                    channel=ch_name,
                    messages=ch_written,
                )

            # 4. Pins
            pin_count = 0
            for ch in msg_targets:
                ch_id = ch.get("id", "")
                if ch.get("is_im") or ch.get("is_mpim"):
                    continue
                try:
                    await self._throttle("pins.list", TIER2_DELAY)
                    data = await self._api(client, "pins.list", {"channel": ch_id})
                    items = data.get("items", [])
                    records = [
                        make_record(
                            "slack",
                            "pin",
                            f"{ch_id}:{p.get('message', {}).get('ts', str(p.get('created', 'unknown')))}",
                            {**p, "_channel": ch_id},
                        )
                        for p in items
                    ]
                    n = await self._write_records(pool, records)
                    pin_count += n
                except Exception:
                    pass
            kinds["pin"] = pin_count
            total += pin_count

            # 5. Bookmarks
            bookmark_count = 0
            for ch in msg_targets:
                ch_id = ch.get("id", "")
                if ch.get("is_im") or ch.get("is_mpim"):
                    continue
                try:
                    await self._throttle("bookmarks.list", TIER2_DELAY)
                    data = await self._api(client, "bookmarks.list", {"channel_id": ch_id})
                    bookmarks = data.get("bookmarks", [])
                    records = [
                        make_record(
                            "slack",
                            "bookmark",
                            b.get("id", "unknown"),
                            {**b, "_channel": ch_id},
                        )
                        for b in bookmarks
                    ]
                    n = await self._write_records(pool, records)
                    bookmark_count += n
                except Exception:
                    pass
            kinds["bookmark"] = bookmark_count
            total += bookmark_count

            # 6. Files
            file_count = 0
            for ch in msg_targets:
                ch_id = ch.get("id", "")
                try:
                    page = 1
                    while True:
                        await self._throttle("files.list", TIER2_DELAY)
                        data = await self._api(
                            client,
                            "files.list",
                            {"channel": ch_id, "count": 100, "page": page},
                        )
                        files = data.get("files", [])
                        if not files:
                            break
                        records = [
                            make_record(
                                "slack",
                                "file",
                                f.get("id", "unknown"),
                                {**f, "_channel": ch_id},
                            )
                            for f in files
                        ]
                        n = await self._write_records(pool, records)
                        file_count += n
                        paging = data.get("paging", {})
                        if page >= paging.get("pages", 1):
                            break
                        page += 1
                except Exception:
                    pass
            kinds["file"] = file_count
            total += file_count

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="slack",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )

    async def _fetch_all_channels(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        all_channels: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            await self._throttle("conversations.list", TIER2_DELAY)
            params: dict[str, Any] = {
                "types": "public_channel,private_channel,im,mpim",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor
            try:
                data = await self._api(client, "conversations.list", params)
            except Exception:
                # Fallback without DMs if missing scope
                params["types"] = "public_channel,private_channel"
                data = await self._api(client, "conversations.list", params)

            all_channels.extend(data.get("channels", []))
            next_cursor = data.get("response_metadata", {}).get("next_cursor", "") or ""
            if not next_cursor:
                break
            cursor = next_cursor
        return all_channels

    async def _fetch_all_users(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        all_users: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            await self._throttle("users.list", TIER2_DELAY)
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await self._api(client, "users.list", params)
            all_users.extend(data.get("members", []))
            next_cursor = data.get("response_metadata", {}).get("next_cursor", "") or ""
            if not next_cursor:
                break
            cursor = next_cursor
        return all_users

    def _filter_message_targets(self, channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        targets = []
        for ch in channels:
            is_dm = ch.get("is_im") or ch.get("is_mpim")
            if is_dm:
                if self._include_dms:
                    targets.append(ch)
            else:
                name = ch.get("name", "")
                if not self._channels or name in self._channels:
                    targets.append(ch)
        return targets

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        channel_id: str,
        oldest: str,
        cursors: CursorStore,
    ) -> tuple[int, str | None]:
        written = 0
        max_ts: str | None = None
        history_cursor: str | None = None

        while True:
            await self._throttle("conversations.history", TIER3_DELAY)
            params: dict[str, Any] = {
                "channel": channel_id,
                "limit": 200,
                "oldest": oldest,
            }
            if history_cursor:
                params["cursor"] = history_cursor

            try:
                data = await self._api(client, "conversations.history", params)
            except Exception as e:
                err_msg = str(e)
                if any(
                    s in err_msg for s in ("not_in_channel", "channel_not_found", "missing_scope")
                ):
                    break
                raise

            messages: list[dict[str, Any]] = data.get("messages", [])
            if not messages:
                break

            # Track max timestamp
            for msg in messages:
                ts = msg.get("ts")
                if ts and (max_ts is None or ts > max_ts):
                    max_ts = ts

            # Write messages
            records = [
                make_record(
                    "slack",
                    "message",
                    f"{channel_id}:{msg.get('ts', 'unknown')}",
                    {**msg, "_channel": channel_id},
                )
                for msg in messages
            ]
            n = await self._write_records(pool, records)
            written += n

            # Fetch thread replies for messages with replies
            threaded = [m for m in messages if m.get("reply_count", 0) > 0 and m.get("ts")]
            for msg in threaded:
                thread_ts = msg["ts"]
                reply_cursor: str | None = None
                while True:
                    await self._throttle("conversations.replies", TIER3_DELAY)
                    rparams: dict[str, Any] = {
                        "channel": channel_id,
                        "ts": thread_ts,
                        "limit": 200,
                    }
                    if reply_cursor:
                        rparams["cursor"] = reply_cursor

                    try:
                        rdata = await self._api(client, "conversations.replies", rparams)
                    except Exception:
                        break

                    replies = [r for r in rdata.get("messages", []) if r.get("ts") != thread_ts]
                    for r in replies:
                        ts = r.get("ts")
                        if ts and (max_ts is None or ts > max_ts):
                            max_ts = ts

                    reply_records = [
                        make_record(
                            "slack",
                            "message",
                            f"{channel_id}:{r.get('ts', 'unknown')}",
                            {
                                **r,
                                "_channel": channel_id,
                                "_thread_ts": thread_ts,
                            },
                        )
                        for r in replies
                    ]
                    rn = await self._write_records(pool, reply_records)
                    written += rn

                    next_cursor = rdata.get("response_metadata", {}).get("next_cursor", "") or ""
                    if not next_cursor:
                        break
                    reply_cursor = next_cursor

            # Check pagination
            next_cursor = data.get("response_metadata", {}).get("next_cursor", "") or ""
            if not next_cursor or not data.get("has_more"):
                break
            history_cursor = next_cursor

        return written, max_ts
