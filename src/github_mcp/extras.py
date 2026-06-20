"""Assorted write/util tools that round out the connector's CRUD coverage.

Fills gaps left by the core tools: syncing a PR branch with its base, editing
and deleting issue/PR comments, deleting and getting a download link for release
assets, deleting a gist, and marking all notifications read. Write tools are
disabled in read-only mode. The package ``__init__`` imports this module to
register them.
"""

from __future__ import annotations

from typing import Any

from .server import _session, _summarize_comment, mcp


@mcp.tool()
async def update_pull_request_branch(
    owner: str, repo: str, pull_number: int, expected_head_sha: str | None = None
) -> dict[str, Any]:
    """Update a PR's branch with the latest from its base (the "Update branch" button).

    Merges the base branch into the PR's head so it's no longer behind. Pass
    `expected_head_sha` to make it a no-op if the head has moved since you
    checked. This is a gated write; the update runs asynchronously on GitHub.
    """
    payload: dict[str, Any] = {}
    if expected_head_sha is not None:
        payload["expected_head_sha"] = expected_head_sha
    async with _session(write=True) as gh:
        result = await gh.put(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/update-branch",
            json=payload,
        )
    return {"updating": True, "message": (result or {}).get("message")}


@mcp.tool()
async def update_issue_comment(
    owner: str, repo: str, comment_id: int, body: str
) -> dict[str, Any]:
    """Edit an existing issue or PR conversation comment (a gated write).

    `comment_id` is the numeric id from `list_issue_comments`. Replaces the
    comment's body.
    """
    async with _session(write=True) as gh:
        comment = await gh.patch(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
    return _summarize_comment(comment)


@mcp.tool()
async def delete_issue_comment(
    owner: str, repo: str, comment_id: int
) -> dict[str, Any]:
    """Delete an issue or PR conversation comment (a gated write)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/issues/comments/{comment_id}")
    return {"deleted": True, "comment_id": comment_id}


@mcp.tool()
async def delete_release_asset(
    owner: str, repo: str, asset_id: int
) -> dict[str, Any]:
    """Delete a release asset by its id (a gated write).

    `asset_id` is from `list_release_assets`.
    """
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/releases/assets/{asset_id}")
    return {"deleted": True, "asset_id": asset_id}


@mcp.tool()
async def download_release_asset(
    owner: str, repo: str, asset_id: int
) -> dict[str, Any]:
    """Get a download link and metadata for a release asset.

    Returns the asset's name, size, content type, and `browser_download_url`.
    The binary itself isn't streamed back over MCP — use the URL to fetch it.
    """
    async with _session() as gh:
        a = await gh.get(f"/repos/{owner}/{repo}/releases/assets/{asset_id}")
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "size": a.get("size"),
        "content_type": a.get("content_type"),
        "download_count": a.get("download_count"),
        "browser_download_url": a.get("browser_download_url"),
    }


@mcp.tool()
async def delete_gist(gist_id: str) -> dict[str, Any]:
    """Delete one of the authenticated user's gists (a gated write)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/gists/{gist_id}")
    return {"deleted": True, "gist_id": gist_id}


@mcp.tool()
async def mark_all_notifications_read(
    last_read_at: str | None = None
) -> dict[str, Any]:
    """Mark all of the authenticated user's notifications as read (a gated write).

    Optionally pass `last_read_at` (ISO 8601) to only mark those read before that
    time; omit to mark everything read.
    """
    payload: dict[str, Any] = {}
    if last_read_at is not None:
        payload["last_read_at"] = last_read_at
    async with _session(write=True) as gh:
        await gh.put("/notifications", json=payload)
    return {"marked_read": True, "last_read_at": last_read_at}
