"""Commit history, diffs between refs, commit statuses, and check runs.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .core import _clamp, _session, mcp
from .summaries import _summarize_check_run, _summarize_commit, _summarize_file


@mcp.tool()
async def list_commits(
    owner: str,
    repo: str,
    sha: str | None = None,
    path: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List recent commits on a repository.

    Optionally narrow to a branch/SHA via `sha` or to commits touching a single
    file via `path`. Returns up to `limit` (max 50) commits.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        commits = await gh.get(
            f"/repos/{owner}/{repo}/commits",
            params={"sha": sha, "path": path, "per_page": limit, "page": page},
        )
    return [_summarize_commit(commit) for commit in commits]


@mcp.tool()
async def get_commit(owner: str, repo: str, ref: str) -> dict[str, Any]:
    """Get a single commit with its stats and changed files.

    `ref` is a commit SHA, branch, or tag. Returns the commit metadata plus
    aggregate additions/deletions and a per-file summary (no patch text).
    """
    async with _session() as gh:
        commit = await gh.get(f"/repos/{owner}/{repo}/commits/{ref}")
    summary = _summarize_commit(commit)
    summary["stats"] = commit.get("stats")
    summary["files"] = [_summarize_file(f) for f in commit.get("files", [])]
    return summary


@mcp.tool()
async def compare_commits(
    owner: str, repo: str, base: str, head: str
) -> dict[str, Any]:
    """Compare two commits, branches, or tags.

    Returns how `head` relates to `base` (`ahead_by`/`behind_by`), the commits
    in between, and the files changed. Useful for "what's on this branch that
    isn't on main" or reviewing a range.
    """
    async with _session() as gh:
        result = await gh.get(f"/repos/{owner}/{repo}/compare/{base}...{head}")
    return {
        "status": result.get("status"),
        "ahead_by": result.get("ahead_by"),
        "behind_by": result.get("behind_by"),
        "total_commits": result.get("total_commits"),
        "commits": [_summarize_commit(c) for c in result.get("commits", [])],
        "files": [_summarize_file(f) for f in result.get("files", [])],
        "html_url": result.get("html_url"),
    }


@mcp.tool()
async def get_combined_status(owner: str, repo: str, ref: str) -> dict[str, Any]:
    """Get the combined commit status for a ref (branch, tag, or SHA).

    Returns the overall `state` (`success`/`pending`/`failure`) and each
    individual status context. This covers the legacy "statuses" API; for
    GitHub Actions checks use `list_check_runs`.
    """
    async with _session() as gh:
        data = await gh.get(f"/repos/{owner}/{repo}/commits/{ref}/status")
    return {
        "state": data.get("state"),
        "total_count": data.get("total_count"),
        "statuses": [
            {
                "context": s.get("context"),
                "state": s.get("state"),
                "description": s.get("description"),
                "target_url": s.get("target_url"),
            }
            for s in data.get("statuses", [])
        ],
    }


@mcp.tool()
async def list_check_runs(
    owner: str, repo: str, ref: str, limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List the check runs for a ref (branch, tag, or SHA).

    These are the GitHub Actions / app check results for the commit. Use this to
    inspect CI on any ref without going through a pull request. Returns up to
    `limit` (max 100) check runs.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        result = await gh.get(
            f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            params={"per_page": limit, "page": page},
        )
    return [_summarize_check_run(c) for c in result.get("check_runs", [])]
