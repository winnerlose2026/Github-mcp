"""Release and tag deletion tools.

The bulk of the connector's release/tag tools live in :mod:`github_mcp.server`
(``create_release``, ``list_releases``, ``list_tags``, ``get_tag``). This module
adds the deletions, which `server` doesn't cover: a release and its git tag are
separate objects on GitHub, so deleting a release leaves the tag behind and vice
versa. ``delete_release_and_tag`` removes both in one call and tolerates either
being already gone. All are writes (disabled in read-only mode) and register on
the shared FastMCP instance; the package ``__init__`` imports this module for
the side effect of registering them.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .server import _session, mcp


@mcp.tool()
async def delete_release(
    owner: str,
    repo: str,
    tag: str | None = None,
    release_id: int | None = None,
) -> dict[str, Any]:
    """Delete a GitHub release (a write; gated by read-only mode).

    Identify the release by either `tag` (e.g. `v0.10.0`) or its numeric
    `release_id`; provide exactly one (`release_id` wins if both are given).
    This deletes only the release — the underlying git tag is left in place; use
    `delete_tag` for that, or `delete_release_and_tag` to remove both. Requires a
    token with write access to the repository.
    """
    if release_id is None and not tag:
        raise GitHubError(
            422,
            "DELETE",
            f"/repos/{owner}/{repo}/releases",
            "Provide either `tag` or `release_id` to identify the release.",
        )
    async with _session(write=True) as gh:
        if release_id is None:
            release = await gh.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
            release_id = release.get("id")
        await gh.delete(f"/repos/{owner}/{repo}/releases/{release_id}")
    return {"deleted_release": True, "release_id": release_id, "tag": tag}


@mcp.tool()
async def delete_tag(owner: str, repo: str, tag: str) -> dict[str, Any]:
    """Delete a git tag (a write; gated by read-only mode).

    Removes the tag ref `refs/tags/<tag>` (pass just the tag name, e.g.
    `v0.10.0`). This touches only the git tag — any release associated with it
    is left in place; use `delete_release` for that, or `delete_release_and_tag`
    to remove both. Requires a token with write access to the repository.
    """
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/git/refs/tags/{tag}")
    return {"deleted_tag": True, "tag": tag, "ref": f"tags/{tag}"}


@mcp.tool()
async def delete_release_and_tag(
    owner: str, repo: str, tag: str
) -> dict[str, Any]:
    """Delete both a release and its git tag in one call (a gated write).

    Convenience for fully retiring a tag like `v0.10.0`: it deletes the release
    published for `tag` (if any) and then the `refs/tags/<tag>` ref. Each step
    tolerates its target already being absent (a 404 is reported as
    `*_deleted: false` rather than failing), so it's safe to run for cleanup.
    Returns which of the two were actually deleted. Requires a token with write
    access to the repository.
    """
    result: dict[str, Any] = {"tag": tag}
    async with _session(write=True) as gh:
        try:
            release = await gh.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
            await gh.delete(f"/repos/{owner}/{repo}/releases/{release.get('id')}")
            result["release_deleted"] = True
            result["release_id"] = release.get("id")
        except GitHubError as exc:
            if exc.status_code == 404:
                result["release_deleted"] = False
                result["release_id"] = None
            else:
                raise
        try:
            await gh.delete(f"/repos/{owner}/{repo}/git/refs/tags/{tag}")
            result["tag_deleted"] = True
        except GitHubError as exc:
            if exc.status_code == 404:
                result["tag_deleted"] = False
            else:
                raise
    return result
