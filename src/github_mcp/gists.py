"""Gists belonging to the authenticated user.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .core import _clamp, _session, mcp
from .summaries import _summarize_gist


@mcp.tool()
async def list_gists(limit: int = 30, page: int = 1) -> list[dict[str, Any]]:
    """List the authenticated user's gists, most recent first (gh gist list).

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on."""
    limit = _clamp(limit, 100)
    async with _session() as gh:
        gists = await gh.get("/gists", params={"per_page": limit, "page": page})
    return [_summarize_gist(gist) for gist in gists]


@mcp.tool()
async def get_gist(gist_id: str) -> dict[str, Any]:
    """Get a single gist, including each file's content (gh gist view).

    Returns the gist's metadata plus a `files` mapping of filename to its text
    content. Large files may be truncated by GitHub.
    """
    async with _session() as gh:
        gist = await gh.get(f"/gists/{gist_id}")
    summary = _summarize_gist(gist)
    summary["files"] = {
        name: info.get("content")
        for name, info in (gist.get("files") or {}).items()
    }
    return summary


@mcp.tool()
async def create_gist(
    files: dict[str, str], description: str | None = None, public: bool = False
) -> dict[str, Any]:
    """Create a gist.

    `files` maps filename -> file content (e.g. `{"notes.md": "# hello"}`).
    `public=False` (default) creates a secret gist. Disabled in read-only mode;
    requires write access.
    """
    payload: dict[str, Any] = {
        "public": public,
        "files": {name: {"content": content} for name, content in files.items()},
    }
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        gist = await gh.post("/gists", json=payload)
    return _summarize_gist(gist)


@mcp.tool()
async def update_gist(
    gist_id: str,
    files: dict[str, str],
    description: str | None = None,
) -> dict[str, Any]:
    """Update a gist's files and/or description (gh gist edit).

    `files` maps filename to new content; an existing filename overwrites that
    file, a new filename adds one. (To rename or delete files, use the gist on
    GitHub.) Disabled in read-only mode; requires write access.
    """
    payload: dict[str, Any] = {
        "files": {name: {"content": content} for name, content in files.items()}
    }
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        gist = await gh.patch(f"/gists/{gist_id}", json=payload)
    return _summarize_gist(gist)


@mcp.tool()
async def delete_gist(gist_id: str) -> dict[str, Any]:
    """Delete one of the authenticated user's gists (a gated write)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/gists/{gist_id}")
    return {"deleted": True, "gist_id": gist_id}
