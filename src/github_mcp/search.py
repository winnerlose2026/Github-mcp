"""GitHub search. Every tool here takes raw qualifiers (e.g. `repo:o/n`, `is:open`).

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .core import _clamp, _session, mcp
from .summaries import _summarize_commit, _summarize_issue, _summarize_repo


@mcp.tool()
async def search_repositories(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search GitHub for repositories matching a query.

    `query` accepts GitHub search syntax, e.g. `language:python topic:mcp` or
    `org:anthropics stars:>100`. Returns up to `limit` (max 50) repositories.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            "/search/repositories", params={"q": query, "per_page": limit, "page": page}
        )
    return [_summarize_repo(item) for item in result.get("items", [])]


@mcp.tool()
async def search_issues(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search issues and pull requests across GitHub using search qualifiers.

    Example queries: `repo:octocat/hello-world is:open label:bug`,
    `is:pr author:octocat is:merged`. Returns up to `limit` (max 50) results.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            "/search/issues",
            params={"q": query, "per_page": limit, "page": page},
        )
    return [_summarize_issue(item) for item in result.get("items", [])]


@mcp.tool()
async def search_code(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search for code across GitHub.

    Example: `addClass in:file language:js repo:jquery/jquery`. A `repo:`,
    `org:`, or `user:` qualifier is usually required by GitHub's code search.
    Returns up to `limit` (max 50) matching files.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            "/search/code",
            params={"q": query, "per_page": limit, "page": page},
        )
    return [
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "repository": (item.get("repository") or {}).get("full_name"),
            "html_url": item.get("html_url"),
        }
        for item in result.get("items", [])
    ]


@mcp.tool()
async def search_pull_requests(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search pull requests across GitHub (gh search prs).

    Wraps GitHub's issue search with an `is:pr` qualifier added automatically, so
    `query` only needs the PR-specific parts, e.g.
    `repo:octocat/hello-world is:open review:required` or `author:octocat is:merged`.
    Returns up to `limit` (max 50) pull requests.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    full_query = query if "is:pr" in query else f"is:pr {query}"
    async with _session() as gh:
        result = await gh.get(
            "/search/issues", params={"q": full_query, "per_page": limit, "page": page}
        )
    return [_summarize_issue(item) for item in result.get("items", [])]


@mcp.tool()
async def search_commits(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search commits across GitHub (gh search commits).

    Example queries: `repo:octocat/hello-world fix bug`, `author:octocat merge`,
    `org:anthropics committer-date:>2024-01-01`. Returns up to `limit` (max 50)
    commits.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            "/search/commits", params={"q": query, "per_page": limit, "page": page}
        )
    return [_summarize_commit(item) for item in result.get("items", [])]


@mcp.tool()
async def search_users(query: str, limit: int = 10, page: int = 1) -> list[dict[str, Any]]:
    """Search for users and organizations on GitHub (gh search users).

    Example queries: `octocat`, `location:berlin language:python`,
    `type:org anthropic`. Returns up to `limit` (max 50) accounts.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            "/search/users", params={"q": query, "per_page": limit, "page": page}
        )
    return [
        {
            "login": item.get("login"),
            "type": item.get("type"),
            "html_url": item.get("html_url"),
        }
        for item in result.get("items", [])
    ]
