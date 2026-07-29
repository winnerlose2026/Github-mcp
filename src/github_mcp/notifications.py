"""Notification inbox: list threads and mark them read.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .core import _clamp, _session, mcp
from .summaries import _summarize_notification


@mcp.tool()
async def list_notifications(
    all: bool = False, participating: bool = False, limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List the authenticated user's notifications across all repositories.

    By default returns only unread notifications; set `all=True` to include read
    ones, or `participating=True` to limit to threads you're directly
    participating in. Each item's `id` is the thread id for
    `mark_notification_read`. Returns up to `limit` (max 50) notifications.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        notifications = await gh.get(
            "/notifications",
            params={"all": all, "participating": participating, "per_page": limit, "page": page},
        )
    return [_summarize_notification(n) for n in notifications]


@mcp.tool()
async def mark_notification_read(thread_id: str) -> dict[str, Any]:
    """Mark a notification thread as read.

    `thread_id` is the `id` from `list_notifications`. Disabled in read-only
    mode; requires write access.
    """
    async with _session(write=True) as gh:
        await gh.patch(f"/notifications/threads/{thread_id}", json={})
    return {"marked_read": True, "thread_id": thread_id}


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
