from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
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
from shared.cursors import CursorStore, track_max_timestamp

try:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account

    _HAS_GOOGLE_AUTH = True
except ImportError:
    _HAS_GOOGLE_AUTH = False

log = structlog.get_logger()

GCAL_API = "https://www.googleapis.com/calendar/v3"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
GDRIVE_API = "https://www.googleapis.com/drive/v3"
GDOCS_API = "https://docs.googleapis.com/v1"
GSHEETS_API = "https://sheets.googleapis.com/v4"
GSLIDES_API = "https://slides.googleapis.com/v1"
GPEOPLE_API = "https://people.googleapis.com/v1"
ACTIVITY_API = "https://driveactivity.googleapis.com/v2/activity:query"

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleExtractor(BaseExtractor):
    source = "google"

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        service_account_key: str = "",
        past_days: int = 90,
        future_days: int = 14,
        company_domain: str = "",
        gmail_query: str = "newer_than:30d",
        gmail_concurrency: int = 5,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._service_account_key = service_account_key
        self._past_days = past_days
        self._future_days = future_days
        self._company_domain = company_domain
        self._gmail_query = gmail_query
        self._gmail_concurrency = gmail_concurrency
        self._access_token: str | None = None
        self._token_expires: float = 0

    async def _ensure_token(self, client: httpx.AsyncClient) -> str:
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        if self._service_account_key:
            self._access_token = await self._service_account_auth(client)
        else:
            self._access_token = await self._oauth2_refresh(client)

        self._token_expires = time.time() + 3500
        return self._access_token

    async def _oauth2_refresh(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def _service_account_auth(self, client: httpx.AsyncClient) -> str:

        if not _HAS_GOOGLE_AUTH:
            raise RuntimeError("google-auth package required for service account auth")

        key_data = json.loads(self._service_account_key)
        creds = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=[
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/documents.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/presentations.readonly",
                "https://www.googleapis.com/auth/contacts.other.readonly",
                "https://www.googleapis.com/auth/directory.readonly",
                "https://www.googleapis.com/auth/drive.activity.readonly",
            ],
        )
        creds.refresh(GoogleRequest())
        return creds.token

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _api(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._ensure_token(client)
        kwargs: dict[str, Any] = {
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": 60.0,
        }
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        if method == "GET":
            resp = await client.get(url, **kwargs)
        else:
            resp = await client.post(url, **kwargs)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            log.warning("google_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                await self._ensure_token(client)
                data = await self._api(
                    client,
                    f"{GCAL_API}/users/me/calendarList",
                    {"maxResults": 1},
                )
                log.info("google_preflight_ok")
                return True
            except Exception as e:
                log.error("google_preflight_failed", error=str(e))
                return False

    async def extract(self, pool: asyncpg.Pool, cursors: CursorStore) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            await self._ensure_token(client)

            # === GCal ===
            n = await self._extract_gcal(client, pool, cursors, kinds)
            total += n

            # === Gmail ===
            n = await self._extract_gmail(client, pool, cursors, kinds)
            total += n

            # === GDrive ===
            n = await self._extract_gdrive(client, pool, cursors, kinds)
            total += n

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="google",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )

    # ---- GCal ----

    async def _extract_gcal(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        cursors: CursorStore,
        kinds: dict[str, int],
    ) -> int:
        written = 0
        now = datetime.now(UTC)
        time_min = (now - timedelta(days=self._past_days)).isoformat()
        time_max = (now + timedelta(days=self._future_days)).isoformat()

        # List calendars
        data = await self._api(
            client,
            f"{GCAL_API}/users/me/calendarList",
            {"maxResults": 250},
        )
        calendars = data.get("items", [])
        records = [make_record("gcal", "calendar", c.get("id", "unknown"), c) for c in calendars]
        n = await self._write_records(pool, records)
        kinds["calendar"] = n
        written += n

        # Discover directory people if company domain set
        cal_targets = [(c["id"], c.get("summary", c["id"])) for c in calendars]
        if self._company_domain:
            try:
                people = await self._list_directory_people(client)
                for p in people:
                    cal_targets.append((p["email"], p["name"]))
                    rec = make_record(
                        "gcal",
                        "calendar",
                        p["email"],
                        {
                            "id": p["email"],
                            "summary": p["name"],
                            "_source": "directory",
                            "_domain": self._company_domain,
                        },
                    )
                    await self._write_records(pool, [rec])
            except Exception:
                log.warning("google_directory_failed")

        # Fetch events per calendar
        event_count = 0
        for cal_id, cal_name in cal_targets:
            cursor_val = await cursors.get(pool, "gcal", "events", cal_id)
            updated_min = cursor_val if cursor_val and cursor_val >= time_min else None

            page_token: str | None = None
            max_updated: str | None = None

            while True:
                params: dict[str, Any] = {
                    "calendarId": cal_id,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 250,
                }
                if page_token:
                    params["pageToken"] = page_token
                if updated_min:
                    params["updatedMin"] = updated_min

                try:
                    data = await self._api(
                        client,
                        f"{GCAL_API}/calendars/{cal_id}/events",
                        params,
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        break
                    raise

                events = data.get("items", [])
                for ev in events:
                    u = ev.get("updated")
                    if u and (max_updated is None or u > max_updated):
                        max_updated = u

                records = [
                    make_record(
                        "gcal",
                        "event",
                        f"{cal_id}::{ev.get('id', f'unknown-{i}')}",
                        {**ev, "_calendarId": cal_id, "_calendarName": cal_name},
                    )
                    for i, ev in enumerate(events)
                ]
                n = await self._write_records(pool, records)
                event_count += n

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            if max_updated:
                overlap = CursorStore.apply_overlap(max_updated)
                await cursors.set(pool, "gcal", "events", overlap, cal_id)

        kinds["event"] = event_count
        written += event_count
        log.info("gcal_done", calendars=len(cal_targets), events=event_count)
        return written

    async def _list_directory_people(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        people: list[dict[str, str]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "readMask": "emailAddresses,names",
                "sources": "DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE",
                "pageSize": 200,
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._api(
                client,
                f"{GPEOPLE_API}/people:listDirectoryPeople",
                params,
            )

            for p in data.get("people", []):
                emails = p.get("emailAddresses", [])
                names = p.get("names", [])
                email = emails[0].get("value", "") if emails else ""
                name = names[0].get("displayName", email) if names else email
                if email and email.endswith(f"@{self._company_domain}"):
                    people.append({"email": email, "name": name})

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return people

    # ---- Gmail ----

    async def _extract_gmail(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        cursors: CursorStore,
        kinds: dict[str, int],
    ) -> int:
        written = 0
        user_id = "me"

        # Build query with cursor
        query = self._gmail_query
        cursor_val = await cursors.get(pool, "gmail", "messages")
        if cursor_val:
            query = f"{query} after:{cursor_val}"

        # List message refs
        all_refs: list[dict[str, str]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "userId": user_id,
                "q": query,
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._api(client, f"{GMAIL_API}/users/{user_id}/messages", params)
            for m in data.get("messages", []):
                all_refs.append({"id": m.get("id", ""), "threadId": m.get("threadId", "")})
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Fetch message details
        max_internal_date = 0
        sem = asyncio.Semaphore(self._gmail_concurrency)

        async def fetch_msg(ref: dict[str, str]) -> dict[str, Any] | None:
            async with sem:
                try:
                    return await self._api(
                        client,
                        f"{GMAIL_API}/users/{user_id}/messages/{ref['id']}",
                        {
                            "format": "metadata",
                            "metadataHeaders": "From,To,Cc,Subject,Date",
                        },
                    )
                except Exception:
                    return None

        tasks = [fetch_msg(ref) for ref in all_refs]
        messages = await asyncio.gather(*tasks)

        msg_records: list[dict[str, Any]] = []
        threads: dict[str, list[str]] = {}
        max_date_epoch = 0

        for msg in messages:
            if msg is None:
                continue
            msg_id = msg.get("id", "")
            thread_id = msg.get("threadId", "")
            internal_date = int(msg.get("internalDate", "0")) // 1000
            if internal_date > max_date_epoch:
                max_date_epoch = internal_date

            msg_records.append(make_record("gmail", "message", msg_id, msg))
            threads.setdefault(thread_id, []).append(msg_id)

        n = await self._write_records(pool, msg_records)
        kinds["message"] = kinds.get("message", 0) + n
        written += n

        # Write threads
        thread_records = [
            make_record(
                "gmail",
                "thread",
                tid,
                {"threadId": tid, "messageIds": mids},
            )
            for tid, mids in threads.items()
        ]
        tn = await self._write_records(pool, thread_records)
        kinds["gmail_thread"] = tn
        written += tn

        if max_date_epoch > 0:
            overlap_epoch = max(max_date_epoch - 300, 0)
            await cursors.set(pool, "gmail", "messages", str(overlap_epoch))

        log.info("gmail_done", messages=len(msg_records), threads=len(threads))
        return written

    # ---- GDrive ----

    async def _extract_gdrive(
        self,
        client: httpx.AsyncClient,
        pool: asyncpg.Pool,
        cursors: CursorStore,
        kinds: dict[str, int],
    ) -> int:
        written = 0

        # List files
        cursor_val = await cursors.get(pool, "gdrive", "files")
        modified_after = CursorStore.apply_overlap(cursor_val) if cursor_val else None

        all_files: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            q = "trashed = false"
            if modified_after:
                q += f" and modifiedTime > '{modified_after}'"

            params: dict[str, Any] = {
                "pageSize": 100,
                "fields": "files(id,name,mimeType,createdTime,modifiedTime,owners,lastModifyingUser,webViewLink,parents),nextPageToken",
                "q": q,
                "orderBy": "modifiedTime desc",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._api(client, f"{GDRIVE_API}/files", params)
            files = data.get("files", [])
            all_files.extend(files)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Write file records
        file_records = [make_record("gdrive", "file", f.get("id", "unknown"), f) for f in all_files]
        n = await self._write_records(pool, file_records)
        kinds["file"] = kinds.get("file", 0) + n
        written += n

        max_modified: str | None = track_max_timestamp(all_files, "modifiedTime")
        if max_modified:
            await cursors.set(pool, "gdrive", "files", max_modified)

        # Fetch Google Docs content
        doc_mime = "application/vnd.google-apps.document"
        sheet_mime = "application/vnd.google-apps.spreadsheet"
        slides_mime = "application/vnd.google-apps.presentation"

        for f in all_files:
            file_id = f.get("id", "")
            mime = f.get("mimeType", "")

            if mime == doc_mime:
                try:
                    doc = await self._api(
                        client,
                        f"{GDOCS_API}/documents/{file_id}",
                        {"includeTabsContent": "true"},
                    )
                    rec = make_record("gdrive", "doc", file_id, doc)
                    dn = await self._write_records(pool, [rec])
                    kinds["doc"] = kinds.get("doc", 0) + dn
                    written += dn

                    # Extract plain text
                    text = _extract_doc_text(doc)
                    if text:
                        txt_rec = make_record(
                            "gdrive",
                            "plain_text",
                            file_id,
                            {"fileId": file_id, "name": f.get("name"), "text": text},
                        )
                        tn = await self._write_records(pool, [txt_rec])
                        kinds["plain_text"] = kinds.get("plain_text", 0) + tn
                        written += tn
                except Exception:
                    log.warning("gdrive_doc_failed", file_id=file_id)

            elif mime == sheet_mime:
                try:
                    sheet = await self._api(
                        client,
                        f"{GSHEETS_API}/spreadsheets/{file_id}",
                        {"includeGridData": "true"},
                    )
                    rec = make_record("gdrive", "sheet", file_id, sheet)
                    sn = await self._write_records(pool, [rec])
                    kinds["sheet"] = kinds.get("sheet", 0) + sn
                    written += sn
                except Exception:
                    log.warning("gdrive_sheet_failed", file_id=file_id)

            elif mime == slides_mime:
                try:
                    pres = await self._api(
                        client,
                        f"{GSLIDES_API}/presentations/{file_id}",
                    )
                    rec = make_record("gdrive", "presentation", file_id, pres)
                    pn = await self._write_records(pool, [rec])
                    kinds["presentation"] = kinds.get("presentation", 0) + pn
                    written += pn
                except Exception:
                    log.warning("gdrive_slides_failed", file_id=file_id)

            # Comments for all files
            try:
                comment_page: str | None = None
                while True:
                    cparams: dict[str, Any] = {
                        "fileId": file_id,
                        "pageSize": 100,
                        "fields": "comments(id,content,resolved,author,createdTime,modifiedTime,replies,anchor,quotedFileContent),nextPageToken",
                    }
                    if comment_page:
                        cparams["pageToken"] = comment_page
                    cdata = await self._api(
                        client,
                        f"{GDRIVE_API}/files/{file_id}/comments",
                        cparams,
                    )
                    comments = cdata.get("comments", [])
                    if comments:
                        crecs = [
                            make_record(
                                "gdrive",
                                "comment",
                                f"{file_id}:{c.get('id', 'unknown')}",
                                {**c, "_fileId": file_id},
                            )
                            for c in comments
                        ]
                        cn = await self._write_records(pool, crecs)
                        kinds["comment"] = kinds.get("comment", 0) + cn
                        written += cn
                    comment_page = cdata.get("nextPageToken")
                    if not comment_page:
                        break
            except Exception:
                pass

            # Permissions
            try:
                pdata = await self._api(
                    client,
                    f"{GDRIVE_API}/files/{file_id}/permissions",
                    {
                        "fields": "permissions(id,type,role,emailAddress,displayName)",
                        "pageSize": 100,
                    },
                )
                perms = pdata.get("permissions", [])
                if perms:
                    precs = [
                        make_record(
                            "gdrive",
                            "permission",
                            f"{file_id}:{p.get('id', 'unknown')}",
                            {**p, "_fileId": file_id},
                        )
                        for p in perms
                    ]
                    pn = await self._write_records(pool, precs)
                    kinds["permission"] = kinds.get("permission", 0) + pn
                    written += pn
            except Exception:
                pass

            # Revisions
            try:
                rdata = await self._api(
                    client,
                    f"{GDRIVE_API}/files/{file_id}/revisions",
                    {
                        "fields": "revisions(id,modifiedTime,lastModifyingUser)",
                        "pageSize": 100,
                    },
                )
                revisions = rdata.get("revisions", [])
                if revisions:
                    rrecs = [
                        make_record(
                            "gdrive",
                            "revision",
                            f"{file_id}:{rv.get('id', 'unknown')}",
                            {**rv, "_fileId": file_id},
                        )
                        for rv in revisions
                    ]
                    rn = await self._write_records(pool, rrecs)
                    kinds["revision"] = kinds.get("revision", 0) + rn
                    written += rn
            except Exception:
                pass

        # Activities
        try:
            act_page: str | None = None
            while True:
                body: dict[str, Any] = {"pageSize": 100}
                if act_page:
                    body["pageToken"] = act_page
                adata = await self._api(client, ACTIVITY_API, method="POST", json_body=body)
                activities = adata.get("activities", [])
                if activities:
                    arecs = [
                        make_record(
                            "gdrive",
                            "activity",
                            f"act-{i}-{a.get('timestamp', '')}",
                            a,
                        )
                        for i, a in enumerate(activities)
                    ]
                    an = await self._write_records(pool, arecs)
                    kinds["activity"] = kinds.get("activity", 0) + an
                    written += an
                act_page = adata.get("nextPageToken")
                if not act_page:
                    break
        except Exception:
            log.warning("gdrive_activities_failed")

        # Shared drives
        try:
            sd_page: str | None = None
            while True:
                sdparams: dict[str, Any] = {
                    "pageSize": 100,
                    "fields": "drives(id,name,createdTime),nextPageToken",
                }
                if sd_page:
                    sdparams["pageToken"] = sd_page
                sddata = await self._api(client, f"{GDRIVE_API}/drives", sdparams)
                drives = sddata.get("drives", [])
                if drives:
                    sdrecs = [
                        make_record(
                            "gdrive",
                            "shared_drive",
                            d.get("id", "unknown"),
                            d,
                        )
                        for d in drives
                    ]
                    sdn = await self._write_records(pool, sdrecs)
                    kinds["shared_drive"] = kinds.get("shared_drive", 0) + sdn
                    written += sdn
                sd_page = sddata.get("nextPageToken")
                if not sd_page:
                    break
        except Exception:
            pass

        # Folders (already included in files, but tag shortcuts)
        folder_mime = "application/vnd.google-apps.shortcut"
        shortcuts = [f for f in all_files if f.get("mimeType") == folder_mime]
        if shortcuts:
            srecs = [
                make_record("gdrive", "shortcut", s.get("id", "unknown"), s) for s in shortcuts
            ]
            sn = await self._write_records(pool, srecs)
            kinds["shortcut"] = sn
            written += sn

        log.info("gdrive_done", files=len(all_files))
        return written


def _extract_doc_text(doc: dict[str, Any]) -> str:
    tabs = doc.get("tabs", [])
    if not tabs:
        body = doc.get("body", {})
        content = body.get("content", [])
        return _extract_body_text(content)

    sections: list[str] = []
    for tab in _flatten_tabs(tabs):
        title = (tab.get("tabProperties") or {}).get("title", "Untitled")
        body = (tab.get("documentTab") or {}).get("body", {})
        content = body.get("content", [])
        text = _extract_body_text(content)
        if len(tabs) > 1:
            sections.append(f"--- Tab: {title} ---\n{text}")
        else:
            sections.append(text)
    return "\n".join(sections)


def _flatten_tabs(tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tab in tabs:
        result.append(tab)
        children = tab.get("childTabs", [])
        if children:
            result.extend(_flatten_tabs(children))
    return result


def _extract_body_text(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for el in paragraph.get("elements", []):
                text_run = el.get("textRun", {})
                if text_run.get("content"):
                    parts.append(text_run["content"])
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    parts.append(_extract_body_text(cell_content))
    return "".join(parts)
