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

BETTERSTACK_API = "https://uptime.betterstack.com"
BACKFILL_DAYS = 90
MAX_TIMELINE_INCIDENTS = 200
CONCURRENCY = 3


class BetterStackExtractor(BaseExtractor):
    source = "betterstack"

    def __init__(
        self,
        api_token: str,
        backfill_days: int = BACKFILL_DAYS,
        rate_limit_delay_ms: int = 500,
        concurrency: int = CONCURRENCY,
    ) -> None:
        self._token = api_token
        self._backfill_days = backfill_days
        self._rate_limit_delay = rate_limit_delay_ms / 1000.0
        self._concurrency = concurrency

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )
    async def _api(
        self,
        client: httpx.AsyncClient,
        url_or_path: str,
    ) -> dict[str, Any]:
        full_url = (
            url_or_path
            if url_or_path.startswith("http")
            else f"{BETTERSTACK_API}{url_or_path}"
        )
        resp = await client.get(
            full_url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            log.warning("betterstack_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def _paginate_jsonapi(
        self,
        client: httpx.AsyncClient,
        initial_path: str,
    ) -> list[dict[str, Any]]:
        all_resources: list[dict[str, Any]] = []
        url: str | None = initial_path

        while url:
            data = await self._api(client, url)
            resources = data.get("data", [])
            included = data.get("included", [])

            # Flatten JSON:API resources
            for r in resources:
                flat: dict[str, Any] = {"id": r.get("id"), **r.get("attributes", {})}
                rels = r.get("relationships", {})
                for rel_name, rel_data in rels.items():
                    ref = rel_data.get("data")
                    if isinstance(ref, dict):
                        flat[f"{rel_name}_id"] = ref.get("id")
                all_resources.append(flat)

            pagination = data.get("pagination", {})
            url = pagination.get("next") if pagination else None
            if url and self._rate_limit_delay > 0:
                await asyncio.sleep(self._rate_limit_delay)

        return all_resources

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._api(client, "/api/v2/monitors")
                monitors = data.get("data", [])
                log.info("betterstack_preflight_ok", monitors=len(monitors))
                return True
            except Exception as e:
                log.error("betterstack_preflight_failed", error=str(e))
                return False

    async def extract(
        self, pool: asyncpg.Pool, cursors: CursorStore
    ) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # 1. Monitors (full refresh)
            monitors = await self._paginate_jsonapi(client, "/api/v2/monitors")
            records = [
                make_record(
                    "betterstack",
                    "monitor",
                    str(m.get("id", "unknown")),
                    m,
                )
                for m in monitors
            ]
            n = await self._write_records(pool, records)
            kinds["monitor"] = n
            total += n
            log.info("betterstack_monitors", count=len(monitors), written=n)

            # 2. Slack integrations (full refresh)
            slack_integrations = await self._paginate_jsonapi(
                client, "/api/v2/slack-integrations"
            )
            records = [
                make_record(
                    "betterstack",
                    "slack-integration",
                    str(s.get("id", "unknown")),
                    s,
                )
                for s in slack_integrations
            ]
            n = await self._write_records(pool, records)
            kinds["slack-integration"] = n
            total += n

            # 3. On-call schedules (per day, incremental)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            on_call_from = (
                datetime.now(timezone.utc) - timedelta(days=self._backfill_days)
            ).strftime("%Y-%m-%d")

            cursor_val = await cursors.get(pool, "betterstack", "on-call")
            if cursor_val and cursor_val > on_call_from:
                on_call_from = cursor_val

            current = datetime.strptime(on_call_from, "%Y-%m-%d")
            end = datetime.strptime(today, "%Y-%m-%d")
            on_call_total = 0

            while current <= end:
                date_str = current.strftime("%Y-%m-%d")
                data = await self._api(
                    client, f"/api/v2/on-calls?date={date_str}"
                )
                resources = data.get("data", [])
                included = data.get("included", [])

                # Build user lookup from included
                user_lookup: dict[str, dict[str, str]] = {}
                for inc in included:
                    if inc.get("type") == "user":
                        attrs = inc.get("attributes", {})
                        user_lookup[inc["id"]] = {
                            "id": inc["id"],
                            "first_name": attrs.get("first_name", ""),
                            "last_name": attrs.get("last_name", ""),
                            "email": attrs.get("email", ""),
                        }

                for r in resources:
                    attrs = r.get("attributes", {})
                    rels = r.get("relationships", {})
                    user_refs = rels.get("on_call_users", {}).get("data", [])
                    users = []
                    if isinstance(user_refs, list):
                        for ref in user_refs:
                            user = user_lookup.get(ref.get("id", ""))
                            if user:
                                users.append(user)
                            else:
                                users.append({
                                    "id": ref.get("id", ""),
                                    "email": ref.get("meta", {}).get("email", ""),
                                })

                    schedule = {
                        "id": r.get("id"),
                        "name": attrs.get("name"),
                        "default_calendar": attrs.get("default_calendar", False),
                        "team_name": attrs.get("team_name", ""),
                        "on_call_users": users,
                        "date": date_str,
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    }
                    rec = make_record(
                        "betterstack",
                        "on-call",
                        f"{r.get('id')}:{date_str}",
                        schedule,
                    )
                    sn = await self._write_records(pool, [rec])
                    on_call_total += sn

                current += timedelta(days=1)
                if self._rate_limit_delay > 0 and current <= end:
                    await asyncio.sleep(self._rate_limit_delay)

            kinds["on-call"] = on_call_total
            total += on_call_total
            await cursors.set(pool, "betterstack", "on-call", today)

            # 4. Incidents (incremental)
            now_ts = time.time()
            backfill_start = now_ts - self._backfill_days * 86400
            cursor_val = await cursors.get(pool, "betterstack", "incident")
            if cursor_val:
                overlap = CursorStore.apply_overlap(cursor_val)
                try:
                    cursor_dt = datetime.fromisoformat(
                        overlap.replace("Z", "+00:00")
                    )
                    cursor_ts = cursor_dt.timestamp()
                    if cursor_ts > backfill_start:
                        backfill_start = cursor_ts
                except ValueError:
                    pass

            from_date = datetime.fromtimestamp(
                backfill_start, tz=timezone.utc
            ).strftime("%Y-%m-%d")

            incidents = await self._paginate_jsonapi(
                client, f"/api/v3/incidents?per_page=50&from={from_date}"
            )
            records = [
                make_record(
                    "betterstack",
                    "incident",
                    str(i.get("id", "unknown")),
                    i,
                )
                for i in incidents
            ]
            n = await self._write_records(pool, records)
            kinds["incident"] = n
            total += n
            log.info("betterstack_incidents", count=len(incidents), written=n)

            # 5. Incident timelines (per incident, concurrent)
            sorted_incidents = sorted(
                incidents,
                key=lambda i: i.get("started_at", ""),
                reverse=True,
            )[:MAX_TIMELINE_INCIDENTS]

            sem = asyncio.Semaphore(self._concurrency)
            timeline_count = 0

            async def fetch_timeline(incident: dict[str, Any]) -> int:
                async with sem:
                    inc_id = str(incident.get("id", ""))
                    if not inc_id:
                        return 0

                    inc_ts = (
                        incident.get("resolved_at")
                        or incident.get("acknowledged_at")
                        or incident.get("started_at")
                    )
                    tl_cursor = await cursors.get(
                        pool, "betterstack", "incident-timeline", inc_id
                    )
                    if tl_cursor and inc_ts and inc_ts <= tl_cursor:
                        return 0

                    try:
                        events = await self._paginate_jsonapi(
                            client,
                            f"/api/v3/incidents/{inc_id}/timeline",
                        )
                        records = [
                            make_record(
                                "betterstack",
                                "incident-timeline",
                                str(e.get("id", "unknown")),
                                {**e, "_incident_id": inc_id},
                            )
                            for e in events
                        ]
                        written = await self._write_records(pool, records)

                        if inc_ts:
                            await cursors.set(
                                pool,
                                "betterstack",
                                "incident-timeline",
                                inc_ts,
                                inc_id,
                            )

                        if self._rate_limit_delay > 0:
                            await asyncio.sleep(self._rate_limit_delay)

                        return written
                    except Exception:
                        return 0

            tasks = [fetch_timeline(inc) for inc in sorted_incidents]
            results = await asyncio.gather(*tasks)
            timeline_count = sum(results)
            kinds["incident-timeline"] = timeline_count
            total += timeline_count

            # Track max started_at
            max_ts = track_max_timestamp(incidents, "started_at")
            if max_ts:
                await cursors.set(pool, "betterstack", "incident", max_ts)

            log.info(
                "betterstack_done",
                monitors=len(monitors),
                incidents=len(incidents),
                timelines=timeline_count,
            )

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="betterstack",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )
