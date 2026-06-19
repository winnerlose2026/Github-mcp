"""Additional release and tag tools.

The bulk of the connector's release/tag tools live in :mod:`github_mcp.server`
(``create_release``, ``list_releases``, ``list_tags``, ``get_tag``). This module
adds the rest: deletions (a release and its git tag are separate objects, so
``delete_release``/``delete_tag`` each touch one and ``delete_release_and_tag``
removes both, tolerating either being already gone), editing (``update_release``),
changelog generation (``generate_release_notes``), and binary assets
(``list_release_assets``/``upload_release_asset``). Writes are disabled in
read-only mode. All register on the shared FastMCP instance; the package
``__init__`` imports this module for the side effect of registering them.
"""

from __future__ import annotations

import base64
from typing import Any

from .client import GitHubError
from .server import _session, _summarize_release, mcp


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


@mcp.tool()
async def update_release(
    owner: str,
    repo: str,
    tag: str | None = None,
    release_id: int | None = None,
    name: str | None = None,
    body: str | None = None,
    new_tag: str | None = None,
    draft: bool | None = None,
    prerelease: bool | None = None,
) -> dict[str, Any]:
    """Edit an existing release (a write; gated by read-only mode).

    Identify the release by either `tag` (e.g. `v1.2.0`) or its numeric
    `release_id` (`release_id` wins if both are given). Pass only the fields you
    want to change: `name`, `body`, `draft`, `prerelease`, or `new_tag` to retag
    it. Requires a token with write access.
    """
    if release_id is None and not tag:
        raise GitHubError(
            422,
            "PATCH",
            f"/repos/{owner}/{repo}/releases",
            "Provide either `tag` or `release_id` to identify the release.",
        )
    payload: dict[str, Any] = {}
    if new_tag is not None:
        payload["tag_name"] = new_tag
    if name is not None:
        payload["name"] = name
    if body is not None:
        payload["body"] = body
    if draft is not None:
        payload["draft"] = draft
    if prerelease is not None:
        payload["prerelease"] = prerelease
    async with _session(write=True) as gh:
        if release_id is None:
            release = await gh.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
            release_id = release.get("id")
        updated = await gh.patch(
            f"/repos/{owner}/{repo}/releases/{release_id}", json=payload
        )
    return _summarize_release(updated)


@mcp.tool()
async def generate_release_notes(
    owner: str,
    repo: str,
    tag_name: str,
    target_commitish: str | None = None,
    previous_tag_name: str | None = None,
) -> dict[str, Any]:
    """Generate release notes (changelog) for a tag without creating a release.

    Returns a suggested `name` and Markdown `body` built from the PRs/commits
    that GitHub would include for `tag_name`. Optionally scope the range with
    `previous_tag_name` and the target branch/commit with `target_commitish`.
    Read-only/non-mutating: it computes notes but creates nothing.
    """
    payload: dict[str, Any] = {"tag_name": tag_name}
    if target_commitish is not None:
        payload["target_commitish"] = target_commitish
    if previous_tag_name is not None:
        payload["previous_tag_name"] = previous_tag_name
    async with _session() as gh:
        notes = await gh.post(
            f"/repos/{owner}/{repo}/releases/generate-notes", json=payload
        )
    return {"name": notes.get("name"), "body": notes.get("body")}


@mcp.tool()
async def list_release_assets(owner: str, repo: str, tag: str) -> list[dict[str, Any]]:
    """List the binary assets attached to a release (by tag, e.g. `v1.2.0`)."""
    async with _session() as gh:
        release = await gh.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
    return [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "label": a.get("label"),
            "size": a.get("size"),
            "content_type": a.get("content_type"),
            "download_count": a.get("download_count"),
            "browser_download_url": a.get("browser_download_url"),
        }
        for a in release.get("assets", [])
    ]


@mcp.tool()
async def upload_release_asset(
    owner: str,
    repo: str,
    tag: str,
    name: str,
    content_base64: str,
    content_type: str = "application/octet-stream",
    label: str | None = None,
) -> dict[str, Any]:
    """Upload a binary asset to a release (a write; gated by read-only mode).

    Attaches a file to the release tagged `tag`. `content_base64` is the file's
    bytes, base64-encoded; `name` is the asset filename and `content_type` its
    MIME type. Requires a token with write access.
    """
    data = base64.b64decode(content_base64)
    params: dict[str, Any] = {"name": name}
    if label is not None:
        params["label"] = label
    async with _session(write=True) as gh:
        release = await gh.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
        # upload_url is templated like ".../assets{?name,label}"; drop the braces.
        upload_url = (release.get("upload_url") or "").split("{", 1)[0]
        asset = await gh.upload(
            upload_url, data=data, content_type=content_type, params=params
        )
    return {
        "id": asset.get("id"),
        "name": asset.get("name"),
        "size": asset.get("size"),
        "state": asset.get("state"),
        "browser_download_url": asset.get("browser_download_url"),
    }
