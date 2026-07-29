"""File contents: read a file or directory, commit a change, delete a file.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

import base64
from typing import Any

from .client import GitHubError
from .core import _session, mcp


@mcp.tool()
async def get_file_contents(
    owner: str, repo: str, path: str, ref: str | None = None
) -> dict[str, Any]:
    """Read a file or list a directory in a repository.

    `path` is the path within the repo (e.g. `src/app.py`). `ref` is an
    optional branch, tag, or commit SHA (defaults to the default branch). For a
    file the decoded text content is returned; for a directory a listing is
    returned instead.
    """
    async with _session() as gh:
        data = await gh.get(
            f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref}
        )

    if isinstance(data, list):
        return {
            "type": "directory",
            "path": path,
            "entries": [
                {"name": e.get("name"), "path": e.get("path"), "type": e.get("type")}
                for e in data
            ],
        }

    encoding = data.get("encoding")
    raw = data.get("content", "")
    if encoding == "base64":
        try:
            text = base64.b64decode(raw).decode("utf-8")
        except UnicodeDecodeError:
            return {
                "type": "file",
                "path": data.get("path"),
                "size": data.get("size"),
                "binary": True,
                "message": "File is binary and cannot be displayed as text.",
                "html_url": data.get("html_url"),
            }
    else:
        text = raw
    return {
        "type": "file",
        "path": data.get("path"),
        "size": data.get("size"),
        "sha": data.get("sha"),
        "content": text,
        "html_url": data.get("html_url"),
    }


@mcp.tool()
async def create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str | None = None,
    sha: str | None = None,
) -> dict[str, Any]:
    """Create a new file or update an existing one (a single commit).

    `content` is the file's text (UTF-8). `message` is the commit message.
    `branch` defaults to the repository's default branch. When updating an
    existing file you must pass its blob `sha`; if you don't, this tool looks it
    up automatically for the target branch. Disabled in read-only mode; requires
    a token with write access.
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {"message": message, "content": encoded}
    if branch is not None:
        payload["branch"] = branch
    async with _session(write=True) as gh:
        if sha is None:
            # If the file already exists, GitHub requires its current blob sha.
            try:
                existing = await gh.get(
                    f"/repos/{owner}/{repo}/contents/{path}",
                    params={"ref": branch},
                )
                if isinstance(existing, dict):
                    sha = existing.get("sha")
            except GitHubError as exc:
                if exc.status_code != 404:
                    raise  # a real error; only 404 (new file) is expected
        if sha is not None:
            payload["sha"] = sha
        result = await gh.put(
            f"/repos/{owner}/{repo}/contents/{path}", json=payload
        )
    commit = result.get("commit", {})
    content_info = result.get("content", {})
    return {
        "path": content_info.get("path", path),
        "sha": content_info.get("sha"),
        "commit_sha": commit.get("sha"),
        "html_url": content_info.get("html_url"),
        "created": sha is None,
    }


@mcp.tool()
async def delete_file(
    owner: str,
    repo: str,
    path: str,
    message: str,
    branch: str | None = None,
    sha: str | None = None,
) -> dict[str, Any]:
    """Delete a file from a repository in a single commit.

    `message` is the commit message. `branch` defaults to the repository's
    default branch. Deleting requires the file's current blob `sha`; if you don't
    pass it, this tool looks it up for the target branch. Disabled in read-only
    mode; requires write access.
    """
    params = {"ref": branch} if branch is not None else None
    payload: dict[str, Any] = {"message": message}
    if branch is not None:
        payload["branch"] = branch
    async with _session(write=True) as gh:
        if sha is None:
            existing = await gh.get(
                f"/repos/{owner}/{repo}/contents/{path}", params=params
            )
            if isinstance(existing, dict):
                sha = existing.get("sha")
        payload["sha"] = sha
        result = await gh.delete(
            f"/repos/{owner}/{repo}/contents/{path}", json=payload
        )
    commit = (result or {}).get("commit", {})
    return {"deleted": True, "path": path, "commit_sha": commit.get("sha")}
