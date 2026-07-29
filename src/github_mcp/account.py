"""Account and quota tools: the token's own identity, other users, rate limits.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .core import _session, mcp


@mcp.tool()
async def get_authenticated_user() -> dict[str, Any]:
    """Return the GitHub account the connector's token authenticates as.

    Useful as a connection/health check and to confirm which identity and
    permissions the connector is operating with.
    """
    async with _session() as gh:
        user = await gh.get("/user")
    return {
        "login": user.get("login"),
        "name": user.get("name"),
        "type": user.get("type"),
        "public_repos": user.get("public_repos"),
        "html_url": user.get("html_url"),
    }


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
