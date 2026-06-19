"""Repository metadata, collaboration, and account tools.

Complements the core repo tools in :mod:`github_mcp.server` (``get_repository``,
``create_repository``, ``fork_repository``). This module adds read tools for a
repo's collaborators, languages, and topics, plus any user's public profile and
the token's rate-limit status; and write tools to update a repository's
settings, replace its topics, and set a commit status. They register on the
shared FastMCP instance and reuse the server's auth/session, so they honor the
same token and read-only policy; the package ``__init__`` imports this module
for the side effect of registering them.
"""

from __future__ import annotations

from typing import Any

from .server import _clamp, _session, _summarize_repo, mcp


@mcp.tool()
async def get_rate_limit() -> dict[str, Any]:
    """Show the token's current GitHub API rate-limit status.

    Returns the remaining/limit/reset for the `core`, `search`, and `graphql`
    buckets — handy for diagnosing 403s or pacing bulk work. Doesn't count
    against the limit itself.
    """
    async with _session() as gh:
        data = await gh.get("/rate_limit")
    resources = data.get("resources", {})
    return {
        name: {
            "limit": bucket.get("limit"),
            "remaining": bucket.get("remaining"),
            "reset": bucket.get("reset"),
        }
        for name, bucket in resources.items()
        if name in ("core", "search", "graphql")
    }


@mcp.tool()
async def get_user(username: str) -> dict[str, Any]:
    """Get a user's or organization's public profile (gh api /users/<name>)."""
    async with _session() as gh:
        user = await gh.get(f"/users/{username}")
    return {
        "login": user.get("login"),
        "name": user.get("name"),
        "type": user.get("type"),
        "company": user.get("company"),
        "location": user.get("location"),
        "bio": user.get("bio"),
        "public_repos": user.get("public_repos"),
        "followers": user.get("followers"),
        "html_url": user.get("html_url"),
    }


@mcp.tool()
async def list_repository_collaborators(
    owner: str, repo: str, limit: int = 30
) -> list[dict[str, Any]]:
    """List a repository's collaborators with their permission level.

    Returns up to `limit` (max 100) collaborators. Requires push (or higher)
    access to the repository.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        users = await gh.get(
            f"/repos/{owner}/{repo}/collaborators", params={"per_page": limit}
        )
    return [
        {
            "login": u.get("login"),
            "type": u.get("type"),
            "permissions": u.get("permissions"),
            "html_url": u.get("html_url"),
        }
        for u in users
    ]


@mcp.tool()
async def list_repository_languages(owner: str, repo: str) -> dict[str, int]:
    """Get the language breakdown of a repository (bytes of code per language)."""
    async with _session() as gh:
        languages = await gh.get(f"/repos/{owner}/{repo}/languages")
    return languages


@mcp.tool()
async def get_repository_topics(owner: str, repo: str) -> dict[str, Any]:
    """List the topics (tags) set on a repository."""
    async with _session() as gh:
        data = await gh.get(f"/repos/{owner}/{repo}/topics")
    return {"names": data.get("names", [])}


@mcp.tool()
async def replace_repository_topics(
    owner: str, repo: str, topics: list[str]
) -> dict[str, Any]:
    """Replace a repository's topics with `topics` (a write; read-only gated).

    This sets the full topic list (it doesn't append) — pass every topic you
    want to keep. Topic names are lowercase, may include hyphens, and there's a
    limit of 20. Requires a token with write access.
    """
    async with _session(write=True) as gh:
        data = await gh.put(
            f"/repos/{owner}/{repo}/topics", json={"names": topics}
        )
    return {"names": data.get("names", [])}


@mcp.tool()
async def update_repository(
    owner: str,
    repo: str,
    name: str | None = None,
    description: str | None = None,
    homepage: str | None = None,
    private: bool | None = None,
    default_branch: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    """Update a repository's settings (a write; gated by read-only mode).

    Pass only the fields you want to change: `name` (rename), `description`,
    `homepage`, `private`, `default_branch`, or `archived`. Requires a token with
    admin access to the repository.
    """
    payload: dict[str, Any] = {}
    for key, value in (
        ("name", name),
        ("description", description),
        ("homepage", homepage),
        ("private", private),
        ("default_branch", default_branch),
        ("archived", archived),
    ):
        if value is not None:
            payload[key] = value
    async with _session(write=True) as gh:
        updated = await gh.patch(f"/repos/{owner}/{repo}", json=payload)
    return _summarize_repo(updated)


@mcp.tool()
async def create_commit_status(
    owner: str,
    repo: str,
    sha: str,
    state: str,
    target_url: str | None = None,
    description: str | None = None,
    context: str = "default",
) -> dict[str, Any]:
    """Set a commit status on a SHA (a write; gated by read-only mode).

    `state` is one of `error`, `failure`, `pending`, or `success`. `context` is
    the status label (e.g. `ci/my-check`); `target_url` links to details and
    `description` is a short summary. Lets the connector report check-style
    results. Requires a token with write access.
    """
    payload: dict[str, Any] = {"state": state, "context": context}
    if target_url is not None:
        payload["target_url"] = target_url
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        status = await gh.post(
            f"/repos/{owner}/{repo}/statuses/{sha}", json=payload
        )
    return {
        "state": status.get("state"),
        "context": status.get("context"),
        "description": status.get("description"),
        "target_url": status.get("target_url"),
    }
