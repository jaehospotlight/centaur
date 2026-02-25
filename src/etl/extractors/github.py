from __future__ import annotations

import asyncio
import subprocess
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

GITHUB_API = "https://api.github.com"


class GitHubExtractor(BaseExtractor):
    source = "github"

    def __init__(
        self,
        token: str,
        org: str = "tempoxyz",
        repos: list[str] | None = None,
        max_pr_pages: int = 10,
    ) -> None:
        self._token = token or _gh_cli_token()
        self._org = org
        self._repos = repos or []
        self._max_pr_pages = max_pr_pages

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _api(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        resp = await client.get(
            f"{GITHUB_API}{path}",
            params=params or {},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            log.warning("github_rate_limited", retry_after=retry_after)
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def preflight(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                data = await self._api(client, "/user")
                log.info("github_preflight_ok", login=data.get("login"))
                return True
            except Exception as e:
                log.error("github_preflight_failed", error=str(e))
                return False

    async def extract(self, pool: asyncpg.Pool, cursors: CursorStore) -> ExtractResult:
        start = time.monotonic()
        kinds: dict[str, int] = {}
        total = 0

        async with httpx.AsyncClient() as client:
            # 1. Repos
            all_repos: list[dict[str, Any]] = []
            page = 1
            while True:
                batch = await self._api(
                    client,
                    f"/orgs/{self._org}/repos",
                    {"per_page": 100, "page": page},
                )
                all_repos.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

            records = [make_record("github", "repo", str(r.get("id", "")), r) for r in all_repos]
            n = await self._write_records(pool, records)
            kinds["repo"] = n
            total += n
            log.info("github_repos", count=len(all_repos), written=n)

            # 2. Members
            all_members: list[dict[str, Any]] = []
            page = 1
            while True:
                batch = await self._api(
                    client,
                    f"/orgs/{self._org}/members",
                    {"per_page": 100, "page": page},
                )
                all_members.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

            records = [
                make_record("github", "member", str(m.get("id", "")), m) for m in all_members
            ]
            n = await self._write_records(pool, records)
            kinds["member"] = n
            total += n
            log.info("github_members", count=len(all_members), written=n)

            # 3. PRs (per repo)
            target_repos = (
                self._repos if self._repos else [r["name"] for r in all_repos if r.get("name")]
            )
            pr_author_logins: set[str] = set()

            for repo in target_repos:
                cursor_val = await cursors.get(pool, "github", "pulls", repo)
                since = CursorStore.apply_overlap(cursor_val) if cursor_val else None

                repo_page = 1
                max_updated: str | None = None
                repo_pr_count = 0

                while repo_page <= self._max_pr_pages:
                    try:
                        prs = await self._api(
                            client,
                            f"/repos/{self._org}/{repo}/pulls",
                            {
                                "state": "all",
                                "sort": "updated",
                                "direction": "desc",
                                "per_page": 100,
                                "page": repo_page,
                            },
                        )
                    except Exception as e:
                        log.warning("github_repo_skip", repo=repo, error=str(e))
                        break

                    if since:
                        prs = [
                            pr
                            for pr in prs
                            if not pr.get("updated_at") or pr["updated_at"] >= since
                        ]

                    if not prs:
                        break

                    for pr in prs:
                        updated = pr.get("updated_at")
                        if updated and (max_updated is None or updated > max_updated):
                            max_updated = updated
                        user = pr.get("user", {})
                        if user and user.get("login"):
                            pr_author_logins.add(user["login"])

                    records = [
                        make_record("github", "pr", str(pr.get("id", "")), {**pr, "repo": repo})
                        for pr in prs
                    ]
                    n = await self._write_records(pool, records)
                    kinds["pr"] = kinds.get("pr", 0) + n
                    total += n
                    repo_pr_count += n

                    if len(prs) < 100:
                        break
                    repo_page += 1

                if max_updated:
                    await cursors.set(pool, "github", "pulls", max_updated, repo)

                log.info("github_prs_repo", repo=repo, written=repo_pr_count)

            # 4. User profiles
            for member in all_members:
                login = member.get("login")
                if login:
                    pr_author_logins.add(login)

            user_logins = [l for l in pr_author_logins if not l.endswith("[bot]")]

            for login in user_logins:
                try:
                    user_data = await self._api(client, f"/users/{login}")
                    records = [make_record("github", "user", login, user_data)]
                    n = await self._write_records(pool, records)
                    kinds["user"] = kinds.get("user", 0) + n
                    total += n
                except Exception:
                    log.warning("github_user_skip", login=login)

            log.info("github_users", count=len(user_logins))

        duration = int((time.monotonic() - start) * 1000)
        return ExtractResult(
            source="github",
            records_written=total,
            kinds=kinds,
            duration_ms=duration,
        )


def _gh_cli_token() -> str:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""
