from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
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

log = structlog.get_logger()

LINEAR_API = "https://api.linear.app/graphql"
MAX_FIRST = 100
ISSUE_AGE_DAYS = 180


ISSUES_WITH_RELATIONS_QUERY = """
query IssuesWithRelations($first: Int!, $after: String, $filter: IssueFilter) {
    issues(first: $first, after: $after, filter: $filter) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id title priority priorityLabel
            createdAt updatedAt completedAt url identifier
            description estimate dueDate sortOrder
            state { id name type color }
            assignee { id name email }
            project { id name }
            team { id name key }
            creator { id name }
            parent { id identifier }
            labels { nodes { id name color } }
            attachments { nodes { id title url sourceType subtitle metadata createdAt updatedAt } }
            history { nodes { id fromStateId toStateId fromAssigneeId toAssigneeId fromPriority toPriority fromTitle toTitle actorId createdAt updatedAt } }
        }
    }
}
"""

CUSTOMERS_QUERY = """
query Customers($first: Int!, $after: String, $filter: CustomerFilter) {
    customers(first: $first, after: $after, filter: $filter) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id name slugId domains externalIds logoUrl revenue size
            slackChannelId url createdAt updatedAt archivedAt
            owner { id name email }
            status { id name color position }
            tier { id name color position }
        }
    }
}
"""

CUSTOMER_NEEDS_QUERY = """
query CustomerNeeds($first: Int!, $after: String, $filter: CustomerNeedFilter) {
    customerNeeds(first: $first, after: $after, filter: $filter) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id body priority createdAt updatedAt archivedAt
            customer { id name domains }
            issue { id identifier title url }
            project { id name }
        }
    }
}
"""

# Simple paginated query template
SIMPLE_QUERY = """
query {entity_name}($first: Int!, $after: String{filter_param}) {{
    {field_name}(first: $first, after: $after{filter_arg}) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {fields} }}
    }}
}}
"""

ENTITY_CONFIGS: dict[str, dict[str, str]] = {
    "initiatives": {
        "fields": "id name description createdAt updatedAt sortOrder color icon status { id name }",
        "filter_type": "InitiativeFilter",
    },
    "projects": {
        "fields": "id name description createdAt updatedAt completedAt url state priority color icon sortOrder startDate targetDate startedAt lead { id name email } members { nodes { id name } }",
        "filter_type": "ProjectFilter",
    },
    "users": {
        "fields": "id name email displayName avatarUrl active admin createdAt updatedAt lastSeen statusEmoji statusLabel",
        "filter_type": "UserFilter",
    },
    "teams": {
        "fields": "id name key description createdAt updatedAt",
        "filter_type": "TeamFilter",
    },
    "comments": {
        "fields": "id body createdAt updatedAt user { id name } issue { id identifier }",
        "filter_type": "CommentFilter",
    },
    "projectUpdates": {
        "fields": "id body health createdAt updatedAt user { id name } project { id name }",
        "filter_type": "ProjectUpdateFilter",
    },
    "issueRelations": {
        "fields": "id type createdAt updatedAt issue { id identifier } relatedIssue { id identifier }",
        "filter_type": "IssueRelationFilter",
    },
    "workflowStates": {
        "fields": "id name type color position createdAt updatedAt team { id name }",
        "filter_type": "WorkflowStateFilter",
    },
    "issueLabels": {
        "fields": "id name color description createdAt updatedAt",
        "filter_type": "IssueLabelFilter",
    },
    "projectMilestones": {
        "fields": "id name description targetDate sortOrder createdAt updatedAt project { id name }",
        "filter_type": "ProjectMilestoneFilter",
    },
    "documents": {
        "fields": "id title content createdAt updatedAt creator { id name } project { id name }",
        "filter_type": "DocumentFilter",
    },
    "cycles": {
        "fields": "id name number startsAt endsAt completedAt createdAt updatedAt team { id name }",
        "filter_type": "CycleFilter",
    },
}


class LinearExtractor(BaseExtractor):
    source = "linear"

    def __init__(self, api_key: str, issue_age_days: int = ISSUE_AGE_DAYS) -> None:
        self._api_key = api_key
        self._issue_age_days = issue_age_days

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _gql(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = await client.post(
            LINEAR_API,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": self._api_key, "Content-Type": "application/json"},
            timeout=60.0,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            log.warning("linear_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise httpx.HTTPStatusError(
                f"GraphQL errors: {data['errors']}",
                request=resp.request,
                response=resp,
            )
        return data.get("data", {})

    async def _fetch_all_pages(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any],
        root_field: str,
    ) -> list[dict[str, Any]]:
        all_nodes: list[dict[str, Any]] = []
        after: str | None = None
        has_next = True

        while has_next:
            vars_copy = {**variables}
            if after:
                vars_copy["after"] = after
            data = await self._gql(client, query, vars_copy)
            connection = data.get(root_field, {})
            nodes = connection.get("nodes", [])
            all_nodes.extend(nodes)
            page_info = connection.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            after = page_info.get("endCursor")

        return all_nodes

    def _build_simple_query(self, entity: str, config: dict[str, str], has_filter: bool) -> str:
        filter_type = config["filter_type"]
        filter_param = f", $filter: {filter_type}" if has_filter else ""
        filter_arg = ", filter: $filter" if has_filter else ""
        return SIMPLE_QUERY.format(
            entity_name=entity.capitalize(),
            field_name=entity,
            fields=config["fields"],
            filter_param=filter_param,
            filter_arg=filter_arg,
        )

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._gql(
                    client,
                    "query { viewer { id name email } }",
                )
                viewer = data.get("viewer", {})
                log.info(
                    "linear_preflight_ok",
                    name=viewer.get("name"),
                    email=viewer.get("email"),
                )
                return True
            except Exception as e:
                log.error("linear_preflight_failed", error=str(e))
                return False

    async def extract(self, pool: asyncpg.Pool, cursors: CursorStore) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # Fetch simple entities
            for entity_name, config in ENTITY_CONFIGS.items():
                cursor_val = await cursors.get(pool, "linear", entity_name)
                since = CursorStore.apply_overlap(cursor_val) if cursor_val else None

                has_filter = since is not None
                query = self._build_simple_query(entity_name, config, has_filter)
                variables: dict[str, Any] = {"first": MAX_FIRST}
                if since:
                    variables["filter"] = {"updatedAt": {"gte": since}}

                nodes = await self._fetch_all_pages(client, query, variables, entity_name)

                kind = entity_name.lower()
                records = [make_record("linear", kind, n.get("id", "unknown"), n) for n in nodes]
                n_written = await self._write_records(pool, records)
                kinds[kind] = n_written
                total += n_written

                max_ts = track_max_timestamp(nodes, "updatedAt")
                if max_ts:
                    await cursors.set(pool, "linear", entity_name, max_ts)

                log.info("linear_entity_done", entity=kind, fetched=len(nodes), written=n_written)

            # Issues with relations (uses special combined query)
            cursor_val = await cursors.get(pool, "linear", "issues")
            since = CursorStore.apply_overlap(cursor_val) if cursor_val else None

            cutoff_ts = time.time() - self._issue_age_days * 86400
            cutoff = datetime.fromtimestamp(cutoff_ts, tz=UTC).isoformat()
            gte = since if since and since > cutoff else cutoff

            issue_vars: dict[str, Any] = {
                "first": MAX_FIRST,
                "filter": {"updatedAt": {"gte": gte}},
            }
            issue_nodes = await self._fetch_all_pages(
                client, ISSUES_WITH_RELATIONS_QUERY, issue_vars, "issues"
            )

            # Extract inline relations from issue nodes
            labels: list[dict[str, Any]] = []
            attachments: list[dict[str, Any]] = []
            history: list[dict[str, Any]] = []

            for issue in issue_nodes:
                issue_id = issue.get("id", "")
                label_nodes = (issue.get("labels") or {}).get("nodes", [])
                for lbl in label_nodes:
                    labels.append(
                        {
                            "id": f"{issue_id}:{lbl.get('id', '')}",
                            "name": lbl.get("name"),
                            "color": lbl.get("color"),
                            "issue_id": issue_id,
                        }
                    )
                att_nodes = (issue.get("attachments") or {}).get("nodes", [])
                for att in att_nodes:
                    attachments.append({**att, "issue_id": issue_id})
                hist_nodes = (issue.get("history") or {}).get("nodes", [])
                for h in hist_nodes:
                    history.append({**h, "issue_id": issue_id})

            # Write issues
            issue_records = [
                make_record("linear", "issue", i.get("id", "unknown"), i) for i in issue_nodes
            ]
            n_written = await self._write_records(pool, issue_records)
            kinds["issue"] = n_written
            total += n_written

            # Write labels
            label_records = [make_record("linear", "issue_label_link", l["id"], l) for l in labels]
            n_written = await self._write_records(pool, label_records)
            kinds["issue_label_link"] = n_written
            total += n_written

            # Write attachments
            att_records = [
                make_record("linear", "attachment", a.get("id", "unknown"), a) for a in attachments
            ]
            n_written = await self._write_records(pool, att_records)
            kinds["attachment"] = n_written
            total += n_written

            # Write history
            hist_records = [
                make_record("linear", "issue_history", h.get("id", "unknown"), h) for h in history
            ]
            n_written = await self._write_records(pool, hist_records)
            kinds["issue_history"] = n_written
            total += n_written

            max_ts = track_max_timestamp(issue_nodes, "updatedAt")
            if max_ts:
                await cursors.set(pool, "linear", "issues", max_ts)

            log.info(
                "linear_issues_done",
                issues=len(issue_nodes),
                labels=len(labels),
                attachments=len(attachments),
                history=len(history),
            )

            # Customers
            cursor_val = await cursors.get(pool, "linear", "customers")
            since = CursorStore.apply_overlap(cursor_val) if cursor_val else None
            cust_vars: dict[str, Any] = {"first": MAX_FIRST}
            if since:
                cust_vars["filter"] = {"updatedAt": {"gte": since}}
            cust_nodes = await self._fetch_all_pages(
                client, CUSTOMERS_QUERY, cust_vars, "customers"
            )
            cust_records = [
                make_record("linear", "customer", c.get("id", "unknown"), c) for c in cust_nodes
            ]
            n_written = await self._write_records(pool, cust_records)
            kinds["customer"] = n_written
            total += n_written
            max_ts = track_max_timestamp(cust_nodes, "updatedAt")
            if max_ts:
                await cursors.set(pool, "linear", "customers", max_ts)

            # Customer needs
            cursor_val = await cursors.get(pool, "linear", "customerneeds")
            since = CursorStore.apply_overlap(cursor_val) if cursor_val else None
            cn_vars: dict[str, Any] = {"first": MAX_FIRST}
            if since:
                cn_vars["filter"] = {"updatedAt": {"gte": since}}
            cn_nodes = await self._fetch_all_pages(
                client, CUSTOMER_NEEDS_QUERY, cn_vars, "customerNeeds"
            )
            cn_records = [
                make_record("linear", "customer_need", c.get("id", "unknown"), c) for c in cn_nodes
            ]
            n_written = await self._write_records(pool, cn_records)
            kinds["customer_need"] = n_written
            total += n_written
            max_ts = track_max_timestamp(cn_nodes, "updatedAt")
            if max_ts:
                await cursors.set(pool, "linear", "customerneeds", max_ts)

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="linear",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )
