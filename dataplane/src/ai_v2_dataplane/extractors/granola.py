from __future__ import annotations

import asyncio
import os
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

from ..cursors import CursorStore, track_max_timestamp
from .base import BaseExtractor, ExtractResult, make_record

log = structlog.get_logger()

GRANOLA_API = "https://api.granola.ai"
ENTERPRISE_API = "https://api.granola.ai/enterprise"
MAX_TRANSCRIPT_DAYS = 30
MAX_TRANSCRIPTS = 200


class GranolaExtractor(BaseExtractor):
    source = "granola"

    def __init__(
        self,
        access_tokens: list[str] | None = None,
        enterprise_api_key: str = "",
        days: int = 90,
        max_transcripts: int = MAX_TRANSCRIPTS,
    ) -> None:
        self._access_tokens = [t for t in (access_tokens or []) if t]
        self._enterprise_api_key = enterprise_api_key
        self._days = days
        self._max_transcripts = max_transcripts

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _post(
        self,
        client: httpx.AsyncClient,
        token: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        resp = await client.post(
            f"{GRANOLA_API}{path}",
            json=body or {},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _enterprise_get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        resp = await client.get(
            f"{ENTERPRISE_API}{path}",
            params=params or {},
            headers={
                "Authorization": f"Bearer {self._enterprise_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            ok_count = 0
            for token in self._access_tokens:
                try:
                    await self._post(client, token, "/v1/get-all-documents", {})
                    ok_count += 1
                except Exception as e:
                    log.warning("granola_preflight_token_failed", error=str(e))

            if self._enterprise_api_key:
                try:
                    await self._enterprise_get(client, "/v1/notes", {"limit": "1"})
                    ok_count += 1
                except Exception as e:
                    log.warning("granola_preflight_enterprise_failed", error=str(e))

            if ok_count > 0:
                log.info("granola_preflight_ok", accounts=ok_count)
                return True

            log.error("granola_preflight_failed")
            return False

    async def extract(
        self, pool: asyncpg.Pool, cursors: CursorStore
    ) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # Personal accounts
            for idx, token in enumerate(self._access_tokens):
                account_label = f"account-{idx + 1}"
                try:
                    n = await self._extract_personal(
                        client, pool, cursors, kinds, token, account_label
                    )
                    total += n
                except Exception as e:
                    log.warning(
                        "granola_account_failed",
                        account=account_label,
                        error=str(e),
                    )

            # Enterprise
            if self._enterprise_api_key:
                try:
                    n = await self._extract_enterprise(
                        client, pool, cursors, kinds
                    )
                    total += n
                except Exception as e:
                    log.warning("granola_enterprise_failed", error=str(e))

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="granola",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )

    async def _extract_personal(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        cursors: CursorStore,
        kinds: dict[str, int],
        token: str,
        account_label: str,
    ) -> int:
        written = 0

        # Fetch all documents
        data = await self._post(client, token, "/v1/get-all-documents", {})
        docs = data if isinstance(data, list) else data.get("documents", [])

        # Write meetings
        records = [
            make_record(
                "granola",
                "meeting",
                d.get("id", "unknown"),
                {**d, "_account": account_label},
            )
            for d in docs
        ]
        n = await self._write_records(pool, records)
        kinds["meeting"] = kinds.get("meeting", 0) + n
        written += n
        log.info("granola_meetings", account=account_label, count=len(docs), written=n)

        # Fetch transcripts for recent meetings
        cutoff_ts = time.time() - MAX_TRANSCRIPT_DAYS * 86400
        from datetime import datetime, timezone
        cutoff = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).isoformat()

        recent = [
            d
            for d in docs
            if d.get("created_at") and d["created_at"] >= cutoff
        ][: self._max_transcripts]

        for doc in recent:
            doc_id = doc.get("id", "")
            try:
                transcript = await self._post(
                    client, token, "/v1/get-transcript", {"document_id": doc_id}
                )
                segments = (
                    transcript
                    if isinstance(transcript, list)
                    else transcript.get("segments", [])
                )
                if segments:
                    rec = make_record("granola", "transcript", doc_id, segments)
                    tn = await self._write_records(pool, [rec])
                    kinds["transcript"] = kinds.get("transcript", 0) + tn
                    written += tn
            except Exception:
                log.debug("granola_transcript_failed", doc_id=doc_id)

        return written

    async def _extract_enterprise(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        cursors: CursorStore,
        kinds: dict[str, int],
    ) -> int:
        written = 0

        cursor_val = await cursors.get(pool, "granola", "enterprise", "notes")
        created_after = CursorStore.apply_overlap(cursor_val) if cursor_val else None

        page_cursor: str | None = None
        has_more = True
        max_created: str | None = None

        while has_more:
            params: dict[str, Any] = {}
            if page_cursor:
                params["cursor"] = page_cursor
            if created_after:
                params["created_after"] = created_after

            try:
                data = await self._enterprise_get(client, "/v1/notes", params)
            except httpx.HTTPStatusError as e:
                if page_cursor and e.response.status_code == 400:
                    break
                raise

            notes = data.get("notes", [])
            for note in notes:
                note_id = note.get("id", "")

                # Get full note with transcript
                try:
                    full = await self._enterprise_get(
                        client, f"/v1/notes/{note_id}"
                    )
                except Exception:
                    full = note

                rec = make_record(
                    "granola",
                    "meeting",
                    note_id,
                    {
                        **full,
                        "_source": "enterprise",
                        "_owner": full.get("owner", {}).get("email", ""),
                    },
                )
                n = await self._write_records(pool, [rec])
                kinds["meeting"] = kinds.get("meeting", 0) + n
                written += n

                transcript = full.get("transcript", [])
                if transcript:
                    trec = make_record("granola", "transcript", note_id, transcript)
                    tn = await self._write_records(pool, [trec])
                    kinds["transcript"] = kinds.get("transcript", 0) + tn
                    written += tn

                created = full.get("created_at")
                if created and (max_created is None or created > max_created):
                    max_created = created

            has_more = data.get("hasMore", False)
            page_cursor = data.get("cursor")

        if max_created:
            await cursors.set(pool, "granola", "enterprise", max_created, "notes")

        log.info("granola_enterprise_done", written=written)
        return written
