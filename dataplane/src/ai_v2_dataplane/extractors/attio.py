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

from ..cursors import CursorStore
from .base import BaseExtractor, ExtractResult, make_record

log = structlog.get_logger()

ATTIO_API = "https://api.attio.com/v2"
PAGE_SIZE = 50
MAX_RECORDS_PER_OBJECT = 5000
MAX_THREADS = 500
MAX_MEETINGS = 2000


class AttioExtractor(BaseExtractor):
    source = "attio"

    def __init__(
        self,
        api_key: str,
        rate_limit_delay_ms: int = 200,
        max_records_per_object: int = MAX_RECORDS_PER_OBJECT,
    ) -> None:
        self._api_key = api_key
        self._rate_limit_delay = rate_limit_delay_ms / 1000.0
        self._max_records = max_records_per_object

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _request(
        self,
        client: httpx.AsyncClient,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{ATTIO_API}{path}"
        kwargs: dict[str, Any] = {
            "headers": {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            "timeout": 30.0,
        }
        if method == "GET":
            resp = await client.get(url, **kwargs)
        else:
            kwargs["json"] = body or {}
            resp = await client.post(url, **kwargs)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "30"))
            log.warning("attio_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def _paginate_offset(
        self,
        client: httpx.AsyncClient,
        path: str,
        method: str = "GET",
        body_base: dict[str, Any] | None = None,
        max_items: int = MAX_RECORDS_PER_OBJECT,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        offset = 0
        while len(all_items) < max_items:
            if method == "POST":
                body = {**(body_base or {}), "limit": PAGE_SIZE, "offset": offset}
                data = await self._request(client, path, method="POST", body=body)
            else:
                sep = "&" if "?" in path else "?"
                full_path = f"{path}{sep}limit={PAGE_SIZE}&offset={offset}"
                data = await self._request(client, full_path)

            items = data.get("data", [])
            all_items.extend(items)
            if len(items) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            if self._rate_limit_delay > 0:
                await asyncio.sleep(self._rate_limit_delay)
        return all_items

    async def _paginate_cursor(
        self,
        client: httpx.AsyncClient,
        path: str,
        params_base: dict[str, str] | None = None,
        max_items: int = MAX_MEETINGS,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(all_items) < max_items:
            params: dict[str, str] = {**(params_base or {}), "limit": str(PAGE_SIZE)}
            if cursor:
                params["page_token"] = cursor
            sep = "&" if "?" in path else "?"
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            data = await self._request(client, f"{path}{sep}{param_str}")
            items = data.get("data", [])
            all_items.extend(items)
            next_cursor = data.get("next_page_token")
            if not next_cursor or len(items) < PAGE_SIZE:
                break
            cursor = next_cursor
            if self._rate_limit_delay > 0:
                await asyncio.sleep(self._rate_limit_delay)
        return all_items

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._request(client, "/workspace_members")
                members = data.get("data", [])
                log.info("attio_preflight_ok", members=len(members))
                return True
            except Exception as e:
                log.error("attio_preflight_failed", error=str(e))
                return False

    async def extract(
        self, pool: asyncpg.Pool, cursors: CursorStore
    ) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # 1. Workspace members
            data = await self._request(client, "/workspace_members")
            members = data.get("data", [])
            records = [
                make_record(
                    "attio",
                    "workspace-member",
                    m.get("id", {}).get("workspace_member_id", "unknown"),
                    m,
                )
                for m in members
            ]
            n = await self._write_records(pool, records)
            kinds["workspace-member"] = n
            total += n

            # 2. Companies
            companies = await self._paginate_offset(
                client,
                "/objects/companies/records/query",
                method="POST",
                body_base={"sorts": [{"attribute": "created_at", "direction": "desc"}]},
            )
            records = [
                make_record(
                    "attio",
                    "company",
                    r.get("id", {}).get("record_id", "unknown"),
                    r,
                )
                for r in companies
            ]
            n = await self._write_records(pool, records)
            kinds["company"] = n
            total += n
            log.info("attio_companies", count=len(companies), written=n)

            # 3. Persons
            persons = await self._paginate_offset(
                client,
                "/objects/people/records/query",
                method="POST",
                body_base={"sorts": [{"attribute": "created_at", "direction": "desc"}]},
            )
            records = [
                make_record(
                    "attio",
                    "person",
                    r.get("id", {}).get("record_id", "unknown"),
                    r,
                )
                for r in persons
            ]
            n = await self._write_records(pool, records)
            kinds["person"] = n
            total += n

            # 4. Deals
            deals = await self._paginate_offset(
                client,
                "/objects/deals/records/query",
                method="POST",
                body_base={"sorts": [{"attribute": "created_at", "direction": "desc"}]},
            )
            records = [
                make_record(
                    "attio",
                    "deal",
                    r.get("id", {}).get("record_id", "unknown"),
                    r,
                )
                for r in deals
            ]
            n = await self._write_records(pool, records)
            kinds["deal"] = n
            total += n

            # 5. Notes
            notes = await self._paginate_offset(client, "/notes")
            records = [
                make_record(
                    "attio",
                    "note",
                    n_item.get("id", {}).get("note_id", "unknown"),
                    n_item,
                )
                for n_item in notes
            ]
            n = await self._write_records(pool, records)
            kinds["note"] = n
            total += n

            # 6. Tasks
            tasks = await self._paginate_offset(client, "/tasks")
            records = [
                make_record(
                    "attio",
                    "task",
                    t.get("id", {}).get("task_id", "unknown"),
                    t,
                )
                for t in tasks
            ]
            n = await self._write_records(pool, records)
            kinds["task"] = n
            total += n

            # 7. Lists + entries
            list_data = await self._request(client, "/lists")
            lists = list_data.get("data", [])
            records = [
                make_record(
                    "attio",
                    "list",
                    l.get("id", {}).get("list_id", "unknown"),
                    l,
                )
                for l in lists
            ]
            n = await self._write_records(pool, records)
            kinds["list"] = n
            total += n

            for lst in lists:
                list_id = lst.get("id", {}).get("list_id", "")
                if not list_id:
                    continue
                entries = await self._paginate_offset(
                    client,
                    f"/lists/{list_id}/entries/query",
                    method="POST",
                )
                records = [
                    make_record(
                        "attio",
                        "list-entry",
                        e.get("id", {}).get("entry_id", "unknown"),
                        e,
                    )
                    for e in entries
                ]
                n = await self._write_records(pool, records)
                kinds["list-entry"] = kinds.get("list-entry", 0) + n
                total += n

            # 8. Threads + comments (per company)
            thread_total = 0
            for company in companies[:100]:
                record_id = company.get("id", {}).get("record_id", "")
                if not record_id:
                    continue
                threads = await self._paginate_offset(
                    client,
                    f"/threads?record_id={record_id}&object=companies",
                    max_items=MAX_THREADS,
                )
                records = [
                    make_record(
                        "attio",
                        "thread",
                        t.get("id", {}).get("thread_id", "unknown"),
                        t,
                    )
                    for t in threads
                ]
                n = await self._write_records(pool, records)
                kinds["thread"] = kinds.get("thread", 0) + n
                total += n
                thread_total += len(threads)

                for thread in threads:
                    comments = thread.get("comments", [])
                    crecs = [
                        make_record(
                            "attio",
                            "comment",
                            c.get("id", {}).get("comment_id", "unknown"),
                            c,
                        )
                        for c in comments
                    ]
                    cn = await self._write_records(pool, crecs)
                    kinds["comment"] = kinds.get("comment", 0) + cn
                    total += cn

                if self._rate_limit_delay > 0:
                    await asyncio.sleep(self._rate_limit_delay)

            # 9. Meetings
            from datetime import datetime, timedelta, timezone

            cutoff = (
                datetime.now(timezone.utc) + timedelta(days=14)
            ).isoformat()
            cursor_val = await cursors.get(pool, "attio", "meeting", "start")
            starts_after = (
                CursorStore.apply_overlap(cursor_val) if cursor_val else None
            )

            meeting_params: dict[str, str] = {"starts_before": cutoff}
            if starts_after:
                meeting_params["starts_after"] = starts_after

            meetings = await self._paginate_cursor(
                client, "/meetings", meeting_params
            )
            records = [
                make_record(
                    "attio",
                    "meeting",
                    m.get("id", {}).get("meeting_id", "unknown"),
                    m,
                )
                for m in meetings
            ]
            n = await self._write_records(pool, records)
            kinds["meeting"] = n
            total += n

            max_start: str | None = None
            for m in meetings:
                s = (m.get("start") or {}).get("datetime")
                if s and (max_start is None or s > max_start):
                    max_start = s
            if max_start:
                await cursors.set(pool, "attio", "meeting", max_start, "start")

            # 10. Call recordings + transcripts
            for meeting in meetings:
                meeting_id = meeting.get("id", {}).get("meeting_id", "")
                if not meeting_id:
                    continue

                recordings = await self._paginate_cursor(
                    client, f"/meetings/{meeting_id}/call_recordings"
                )
                if not recordings:
                    continue

                rrecs = [
                    make_record(
                        "attio",
                        "call-recording",
                        r.get("id", {}).get("call_recording_id", "unknown"),
                        r,
                    )
                    for r in recordings
                ]
                rn = await self._write_records(pool, rrecs)
                kinds["call-recording"] = kinds.get("call-recording", 0) + rn
                total += rn

                for rec in recordings:
                    rec_id = rec.get("id", {}).get("call_recording_id", "")
                    if rec.get("status") != "completed" or not rec_id:
                        continue
                    try:
                        transcript = await self._request(
                            client,
                            f"/meetings/{meeting_id}/call_recordings/{rec_id}/transcript",
                        )
                        trec = make_record("attio", "transcript", rec_id, transcript)
                        tn = await self._write_records(pool, [trec])
                        kinds["transcript"] = kinds.get("transcript", 0) + tn
                        total += tn
                    except Exception:
                        pass

            log.info(
                "attio_done",
                companies=len(companies),
                persons=len(persons),
                meetings=len(meetings),
                threads=thread_total,
            )

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="attio",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )
