"""Paradigm events operations tool.

Compound operations over Google Sheets and Drive for the events team.
Provides navigation (find events, list folders) and adaptive reading
(auto-detect headers, fuzzy tab matching). Does NOT hardcode column
names or tab schemas — sheets vary per event and the agent interprets.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import re
from typing import Any

# ── Known spreadsheet and folder IDs ─────────────────────────────────────────

EVENTS_DRIVE_ID = "0AFJxLIllfZeTUk9PVA"
EVENTS_2026_FOLDER = "1PlIv4c4lj3Z6lqQbs0rHnB1bBuXDFzRw"
PROGRAM_SHEET_ID = "12AcxHloTv_qGK9XUtbsAKseheeaEtjh_f9Wu8u_rUUo"
MET_TEMPLATE_ID = "1745-b0QCaA8pX-59F4bZl0Bmxmjyk7M8xyi1wrXsYTI"
CONFERENCE_TRACKER_ID = "1AgNeNaIVgWl7jIovJsvW-F1zIz150e-nCr4VCE56odE"
VENUE_TRACKER_ID = "145yxOa6276r9i80Lz-KWkhAvWFR9SKNCYmYcnfF5KVQ"
MARKETING_CALENDAR_ID = "1M7Nx14_wTttY4JawQNwNUcVAfLV0duKAlGr_evbHRbM"
VENUE_SOURCING_ID = "1LxvUqhIMRfEUtNphJ9CLZbcX0VJRJfHVWeC5M7utlp0"
INVITE_PROCESS_ID = "12Ic0DTLKQTJi6T2nyMeyzIty560zJ8gA6cxCQ7EJZWA"
SF_ATTENDEES_ID = "1Tb4moO5FhjD2Ckug2ssdmNEqgMwH98-SxviczSiDtWA"

PAST_EVENTS_FOLDER = "1OfcwrzbzAz84T5BWkZ2xZCBMGMhGVVUS"
VENUE_SPACES_FOLDER = "12ENgWpIzoEW4Kogo-EkcN3_SFE6P7aS6"
RESOURCES_FOLDER = "1da12_Hp4EOqXC4PCRcG4OLktDdvofbIi"
IDEAS_FOLDER = "1DQlTSzsODJ3km_E8YG0y0a6HAhBoazFg"
RECEIPTS_FOLDER = "1WRYaCmdJrR_zoFIzXXrdmkORhSVSU_8a"
STRATEGY_FOLDER = "1800fpvYIH1e1RgBBFFf90u_nu9Ofy8kg"

GSUITE_ACCOUNT = "svc_ai@paradigm.xyz"


_GSUITE_MOD = None


def _gs():
    """Lazy-init gsuite client with the events service account."""
    global _GSUITE_MOD
    if _GSUITE_MOD is None:
        gsuite_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "gsuite", "client.py"
        )
        spec = importlib.util.spec_from_file_location("_gsuite_client_mod", gsuite_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GSUITE_MOD = mod
    _GSUITE_MOD.set_account(GSUITE_ACCOUNT)
    return _GSUITE_MOD.GSuiteClient()


def _normalize(name: str) -> str:
    return name.lower().strip().replace("-", " ").replace("_", " ")


def _parse_rows(data: dict) -> list[dict]:
    """Convert sheets_read output to list of dicts, using headers if present."""
    headers = data.get("headers", [])
    rows = data.get("rows", [])
    if not headers:
        return rows if isinstance(rows, list) else []
    return [
        {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        if isinstance(row, list)
        else row
        for row in rows
    ]


def _find_name_keys(row: dict) -> list[str]:
    """Extract plausible identity keys from a row by looking for name/email-like fields."""
    keys: list[str] = []
    for header, val in row.items():
        h = header.lower()
        if not val or not str(val).strip():
            continue
        if "email" in h or h in ("name", "full name", "fullname"):
            keys.append(str(val).strip().lower())
    first = str(row.get("First Name", row.get("first name", row.get("first", "")))).strip()
    last = str(row.get("Last Name", row.get("last name", row.get("last", "")))).strip()
    if first or last:
        keys.append(f"{first} {last}".strip().lower())
    return [k for k in keys if k]


def _find_category(row: dict) -> str:
    """Find the best category/sector/type field in a row, whatever it's called."""
    for header in ("Sector/Category", "Sector", "Category", "Type", "Role", "Group"):
        val = row.get(header, "")
        if not val:
            for k in row:
                if k.lower() == header.lower():
                    val = row[k]
                    break
        if val and str(val).strip():
            return str(val).strip()
    return "Uncategorized"


class EventsClient:
    """Paradigm events operations — adaptive reading over Sheets and Drive."""

    # ── Generic sheet operations ─────────────────────────────────────────

    def read_sheet(
        self,
        spreadsheet_id: str,
        tab: str | None = None,
        range_notation: str | None = None,
        max_rows: int = 1000,
    ) -> dict:
        """Read any spreadsheet tab and return structured data.

        If tab is given, reads that tab. If range_notation is given, uses it directly.
        Otherwise reads the full sheet. Auto-detects headers from the first
        populated row. Returns headers, rows as dicts, and raw data.
        """
        gs = _gs()
        if range_notation:
            notation = range_notation
        elif tab:
            notation = f"'{tab}'!A1:AZ{max_rows}"
        else:
            notation = f"A1:AZ{max_rows}"
        data = gs.sheets_read(spreadsheet_id, notation)
        rows = _parse_rows(data)
        return {
            "spreadsheet_id": spreadsheet_id,
            "tab": tab,
            "headers": data.get("headers", []),
            "row_count": len(rows),
            "rows": rows,
        }

    def list_tabs(self, spreadsheet_id: str) -> list[str]:
        """List all tab/sheet names in a spreadsheet.

        Useful for discovering what data exists before reading specific tabs.
        """
        gs = _gs()
        data = gs.sheets_read(spreadsheet_id, "A1:A1")
        raw = data.get("raw_values", data)
        if isinstance(raw, dict) and "sheet_names" in raw:
            return raw["sheet_names"]
        with contextlib.suppress(Exception):
            svc = gs._sheets_service()
            meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            return [s["properties"]["title"] for s in meta.get("sheets", [])]
        return []

    # ── Navigation & discovery ───────────────────────────────────────────

    def find_event_tracker(self, event_name: str) -> dict:
        """Find a specific event's spreadsheet in the Events Drive.

        Searches the 2026 Events folder first (by subfolder), then falls back
        to broad Drive search. Returns spreadsheet ID, URL, tab list,
        and available summary data.
        """
        gs = _gs()
        folders = gs.drive_list(folder_id=EVENTS_2026_FOLDER, max_results=50)
        needle = _normalize(event_name)

        event_folder = None
        for f in folders:
            if needle in _normalize(f.get("name", "")) and "folder" in f.get("mimeType", ""):
                event_folder = f
                break

        search_scope = (
            gs.drive_list(folder_id=event_folder["id"], max_results=30)
            if event_folder
            else gs.drive_list(query=event_name, max_results=10)
        )

        spreadsheets = [
            f
            for f in search_scope
            if "spreadsheet" in f.get("mimeType", "") or "tracker" in f.get("name", "").lower()
        ]

        if not spreadsheets:
            return {"found": False, "query": event_name, "results": search_scope}

        best = spreadsheets[0]
        sid = best.get("id", "")
        out: dict[str, Any] = {
            "found": True,
            "spreadsheet_id": sid,
            "name": best.get("name", ""),
            "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit",
        }

        if sid:
            out["tabs"] = self.list_tabs(sid)

        return out

    def get_event_folder_contents(self, event_name: str) -> list[dict]:
        """List all files in a specific event's folder within 2026 Events."""
        gs = _gs()
        folders = gs.drive_list(folder_id=EVENTS_2026_FOLDER, max_results=50)
        needle = _normalize(event_name)
        for f in folders:
            if needle in _normalize(f.get("name", "")) and "folder" in f.get("mimeType", ""):
                return gs.drive_list(folder_id=f["id"], max_results=50)
        return []

    def search_events_drive(self, query: str) -> list[dict]:
        """Search the Events shared drive for documents matching the query."""
        gs = _gs()
        results = gs.drive_list(query=query, max_results=20)
        return [
            {
                "name": f.get("name", ""),
                "type": f.get("mimeType", ""),
                "id": f.get("id", ""),
                "url": (
                    f"https://docs.google.com/spreadsheets/d/{f['id']}/edit"
                    if "spreadsheet" in f.get("mimeType", "")
                    else f"https://drive.google.com/file/d/{f['id']}/view"
                    if f.get("id")
                    else ""
                ),
            }
            for f in results
        ]

    # ── Cross-referencing ────────────────────────────────────────────────

    def compare_sheets(
        self,
        source_id: str,
        target_id: str,
        source_tab: str | None = None,
        target_tab: str | None = None,
    ) -> dict:
        """Cross-reference two sheets and return people in source but not in target.

        Auto-detects name and email columns from headers — works regardless of
        whether columns are called "Email", "email address", "Name", "Full Name",
        "First Name"/"Last Name", etc. Results are categorized by whatever
        sector/category/type column exists.
        """
        source = self.read_sheet(source_id, tab=source_tab)
        target = self.read_sheet(target_id, tab=target_tab)

        target_keys: set[str] = set()
        for row in target["rows"]:
            if isinstance(row, dict):
                target_keys.update(_find_name_keys(row))

        missing: list[dict] = []
        for row in source["rows"]:
            if not isinstance(row, dict):
                continue
            row_keys = _find_name_keys(row)
            if not row_keys:
                continue
            if not any(k in target_keys for k in row_keys):
                missing.append(row)

        categories: dict[str, list[dict]] = {}
        for person in missing:
            cat = _find_category(person)
            categories.setdefault(cat, []).append(person)

        return {
            "source_count": len(source["rows"]),
            "target_count": len(target["rows"]),
            "missing_count": len(missing),
            "categories": {cat: len(ppl) for cat, ppl in categories.items()},
            "missing_by_category": categories,
        }

    # ── Program-level views ──────────────────────────────────────────────

    def get_program_overview(self) -> dict:
        """Get the full 2026 events program with dates, budgets, DRIs, tiers."""
        data = self.read_sheet(PROGRAM_SHEET_ID, tab="2026 Events")
        events = data["rows"]
        quarters: dict[str, int] = {}
        total_budget = 0.0
        for evt in events:
            if not isinstance(evt, dict):
                continue
            q = str(evt.get("Quarter", ""))
            if q.startswith("Q"):
                quarters[q] = quarters.get(q, 0) + 1
            for budget_col in ("Estimate", "2026 Proposed Budget", "Budget"):
                raw = evt.get(budget_col, "")
                if raw:
                    with contextlib.suppress(ValueError, TypeError, AttributeError):
                        total_budget += float(
                            str(raw).replace("$", "").replace(",", "").strip() or "0"
                        )
                    break
        return {
            "spreadsheet_id": PROGRAM_SHEET_ID,
            "events": events,
            "event_count": len(events),
            "quarters": quarters,
            "total_budget_estimate": total_budget,
        }

    def get_upcoming_events(self, days: int = 30) -> dict:
        """Get events in the next N days from both Paradigm-hosted and conference tracker."""
        from datetime import date, datetime, timedelta

        today = date.today()
        cutoff = today + timedelta(days=days)
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

        program = self.read_sheet(PROGRAM_SHEET_ID, tab="2026 Events")
        conferences = self.read_sheet(CONFERENCE_TRACKER_ID, tab="2026 Conferences")

        upcoming: list[dict] = []

        def _try_parse_date(row: dict) -> date | None:
            for col in ("Start Date", "Date", "start_date", "date"):
                raw = str(row.get(col, ""))
                m = date_pattern.search(raw)
                if m:
                    with contextlib.suppress(ValueError):
                        return datetime.strptime(m.group(), "%Y-%m-%d").date()
            return None

        for evt in program["rows"]:
            if not isinstance(evt, dict):
                continue
            dt = _try_parse_date(evt)
            if dt and today <= dt <= cutoff:
                upcoming.append(
                    {
                        "name": evt.get("Event Name", evt.get("event_name", "")),
                        "date": str(dt),
                        "location": evt.get("Location", ""),
                        "type": "paradigm_hosted",
                    }
                )

        for evt in conferences["rows"]:
            if not isinstance(evt, dict):
                continue
            dt = _try_parse_date(evt)
            if dt and today <= dt <= cutoff:
                upcoming.append(
                    {
                        "name": evt.get("Event Name", evt.get("event_name", "")),
                        "date": str(dt),
                        "location": evt.get("Location", ""),
                        "type": "conference",
                    }
                )

        upcoming.sort(key=lambda x: x.get("date", ""))
        return {"period_days": days, "count": len(upcoming), "events": upcoming}

    def get_conference_calendar(self, quarter: str | None = None) -> dict:
        """Get the external conference calendar, optionally filtered by quarter."""
        data = self.read_sheet(CONFERENCE_TRACKER_ID, tab="2026 Conferences")
        conferences = data["rows"]
        if quarter:
            q_upper = quarter.upper()
            conferences = [
                c
                for c in conferences
                if isinstance(c, dict) and q_upper in str(c.get("Quarter", "")).upper()
            ]
        return {
            "spreadsheet_id": CONFERENCE_TRACKER_ID,
            "count": len(conferences),
            "conferences": conferences,
        }


def _client() -> EventsClient:
    return EventsClient()
