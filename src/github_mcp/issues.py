"""Additional issue, milestone, and pull-request tools.

Complements the core issue/PR tools in :mod:`github_mcp.server` (``list_issues``,
``create_issue``, ``update_issue``). This module adds milestones
(``list_milestones``/``create_milestone``), issue locking
(``lock_issue``/``unlock_issue``), and a PR's commit list
(``list_pull_request_commits``). They register on the shared FastMCP instance
and reuse the server's auth/session and summarizers, so they honor the same
token and read-only policy; the package ``__init__`` imports this module for the
side effect of registering them.
"""

from __future__ import annotations

from typing import Any

from .server import _clamp, _session, _summarize_commit, mcp


@mcp.tool()
async def list_milestones(
    owner: str, repo: str, state: str = "open", limit: int = 30
) -> list[dict[str, Any]]:
    """List a repository's milestones.

    `state` is `open`, `closed`, or `all`. Returns up to `limit` (max 100)
    milestones with their number, title, state, and open/closed issue counts.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        milestones = await gh.get(
            f"/repos/{owner}/{repo}/milestones",
            params={"state": state, "per_page": limit},
        )
    return [
        {
            "number": m.get("number"),
            "title": m.get("title"),
            "state": m.get("state"),
            "open_issues": m.get("open_issues"),
            "closed_issues": m.get("closed_issues"),
            "due_on": m.get("due_on"),
            "html_url": m.get("html_url"),
        }
        for m in milestones
    ]


@mcp.tool()
async def create_milestone(
    owner: str,
    repo: str,
    title: str,
    state: str = "open",
    description: str | None = None,
    due_on: str | None = None,
) -> dict[str, Any]:
    """Create a milestone (a write; gated by read-only mode).

    `title` is required; `due_on` is an ISO-8601 timestamp (e.g.
    `2026-12-31T00:00:00Z`). Returns the new milestone's number, which you can
    set on issues via `update_issue`. Requires a token with write access.
    """
    payload: dict[str, Any] = {"title": title, "state": state}
    if description is not None:
        payload["description"] = description
    if due_on is not None:
        payload["due_on"] = due_on
    async with _session(write=True) as gh:
        milestone = await gh.post(
            f"/repos/{owner}/{repo}/milestones", json=payload
        )
    return {
        "number": milestone.get("number"),
        "title": milestone.get("title"),
        "state": milestone.get("state"),
        "html_url": milestone.get("html_url"),
    }


@mcp.tool()
async def lock_issue(
    owner: str,
    repo: str,
    issue_number: int,
    lock_reason: str | None = None,
) -> dict[str, Any]:
    """Lock an issue or PR conversation (a write; gated by read-only mode).

    `lock_reason`, if given, is one of `off-topic`, `too heated`, `resolved`, or
    `spam`. Locking limits new comments to users with write access. Requires a
    token with write access.
    """
    payload = {"lock_reason": lock_reason} if lock_reason is not None else {}
    async with _session(write=True) as gh:
        await gh.put(
            f"/repos/{owner}/{repo}/issues/{issue_number}/lock", json=payload
        )
    return {"locked": True, "issue_number": issue_number, "lock_reason": lock_reason}


@mcp.tool()
async def unlock_issue(
    owner: str, repo: str, issue_number: int
) -> dict[str, Any]:
    """Unlock a previously locked issue or PR (a write; read-only gated)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/issues/{issue_number}/lock")
    return {"locked": False, "issue_number": issue_number}


@mcp.tool()
async def list_pull_request_commits(
    owner: str, repo: str, pull_number: int, limit: int = 50
) -> list[dict[str, Any]]:
    """List the commits that make up a pull request.

    Returns up to `limit` (max 100) commits in the PR, each with its SHA,
    message, author, and date.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        commits = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/commits",
            params={"per_page": limit},
        )
    return [_summarize_commit(c) for c in commits]
