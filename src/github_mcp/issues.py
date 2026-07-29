"""Issues: read/write, comments, labels, assignees, milestones, locking.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .client import GitHubError
from .core import _clamp, _session, mcp
from .summaries import _summarize_comment, _summarize_commit, _summarize_issue


@mcp.tool()
async def list_milestones(
    owner: str, repo: str, state: str = "open", limit: int = 30
) -> list[dict[str, Any]]:
    """List a repository's milestones.

    `state` is `open`, `closed`, or `all`. Returns up to `limit` (max 100)
    milestones with their number, title, state, and open/closed issue counts.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        milestones = await gh.get(
            f"/repos/{owner}/{repo}/milestones",
            params={"state": state, "per_page": limit},
        )
    return [
        {
            "number": m.get("number"),
            "title": m.get("title"),
            "state": m.get("state"),
            "open_issues": m.get("open_issues"),
            "closed_issues": m.get("closed_issues"),
            "due_on": m.get("due_on"),
            "html_url": m.get("html_url"),
        }
        for m in milestones
    ]


@mcp.tool()
async def create_milestone(
    owner: str,
    repo: str,
    title: str,
    state: str = "open",
    description: str | None = None,
    due_on: str | None = None,
) -> dict[str, Any]:
    """Create a milestone (a write; gated by read-only mode).

    `title` is required; `due_on` is an ISO-8601 timestamp (e.g.
    `2026-12-31T00:00:00Z`). Returns the new milestone's number, which you can
    set on issues via `update_issue`. Requires a token with write access.
    """
    payload: dict[str, Any] = {"title": title, "state": state}
    if description is not None:
        payload["description"] = description
    if due_on is not None:
        payload["due_on"] = due_on
    async with _session(write=True) as gh:
        milestone = await gh.post(
            f"/repos/{owner}/{repo}/milestones", json=payload
        )
    return {
        "number": milestone.get("number"),
        "title": milestone.get("title"),
        "state": milestone.get("state"),
        "html_url": milestone.get("html_url"),
    }


@mcp.tool()
async def lock_issue(
    owner: str,
    repo: str,
    issue_number: int,
    lock_reason: str | None = None,
) -> dict[str, Any]:
    """Lock an issue or PR conversation (a write; gated by read-only mode).

    `lock_reason`, if given, is one of `off-topic`, `too heated`, `resolved`, or
    `spam`. Locking limits new comments to users with write access. Requires a
    token with write access.
    """
    payload = {"lock_reason": lock_reason} if lock_reason is not None else {}
    async with _session(write=True) as gh:
        await gh.put(
            f"/repos/{owner}/{repo}/issues/{issue_number}/lock", json=payload
        )
    return {"locked": True, "issue_number": issue_number, "lock_reason": lock_reason}


@mcp.tool()
async def unlock_issue(
    owner: str, repo: str, issue_number: int
) -> dict[str, Any]:
    """Unlock a previously locked issue or PR (a write; read-only gated)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/issues/{issue_number}/lock")
    return {"locked": False, "issue_number": issue_number}


@mcp.tool()
async def list_pull_request_commits(
    owner: str, repo: str, pull_number: int, limit: int = 50
) -> list[dict[str, Any]]:
    """List the commits that make up a pull request.

    Returns up to `limit` (max 100) commits in the PR, each with its SHA,
    message, author, and date.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        commits = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/commits",
            params={"per_page": limit},
        )
    return [_summarize_commit(c) for c in commits]


@mcp.tool()
async def list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List issues in a repository.

    `state` is one of `open`, `closed`, or `all`. `labels` is an optional
    comma-separated list of label names to filter by. Note: GitHub's issues
    endpoint also returns pull requests; check `is_pull_request` on each item.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        issues = await gh.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "labels": labels, "per_page": limit},
        )
    return [_summarize_issue(issue) for issue in issues]


@mcp.tool()
async def get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    """Get a single issue including its full body text."""
    async with _session() as gh:
        issue = await gh.get(f"/repos/{owner}/{repo}/issues/{issue_number}")
    summary = _summarize_issue(issue)
    summary["body"] = issue.get("body")
    return summary


@mcp.tool()
async def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new issue in a repository.

    Disabled when the connector runs in read-only mode. Requires a token with
    write access to the repository.
    """
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    async with _session(write=True) as gh:
        issue = await gh.post(f"/repos/{owner}/{repo}/issues", json=payload)
    summary = _summarize_issue(issue)
    summary["body"] = issue.get("body")
    return summary


@mcp.tool()
async def update_issue(
    owner: str,
    repo: str,
    issue_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Edit an existing issue: change its title, body, labels, or state.

    Pass `state` as `closed` to close an issue or `open` to reopen it. Only the
    fields you provide are changed. Disabled in read-only mode; requires a token
    with write access.
    """
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if labels is not None:
        payload["labels"] = labels
    if not payload:
        raise GitHubError(
            400,
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            "Nothing to update: provide at least one of title, body, state, labels.",
        )
    async with _session(write=True) as gh:
        issue = await gh.patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}", json=payload
        )
    summary = _summarize_issue(issue)
    summary["body"] = issue.get("body")
    return summary


@mcp.tool()
async def add_issue_comment(
    owner: str, repo: str, issue_number: int, body: str
) -> dict[str, Any]:
    """Add a comment to an issue or pull request.

    Disabled when the connector runs in read-only mode. Requires a token with
    write access to the repository.
    """
    async with _session(write=True) as gh:
        comment = await gh.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
    return {
        "id": comment.get("id"),
        "user": (comment.get("user") or {}).get("login"),
        "html_url": comment.get("html_url"),
        "created_at": comment.get("created_at"),
    }


@mcp.tool()
async def list_issue_comments(
    owner: str, repo: str, issue_number: int, limit: int = 30
) -> list[dict[str, Any]]:
    """List the conversation comments on an issue or pull request.

    These are the top-level timeline comments (not inline code-review comments —
    use `list_pull_request_review_comments` for those). Returns up to `limit`
    (max 100) comments.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        comments = await gh.get(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            params={"per_page": limit},
        )
    return [_summarize_comment(c) for c in comments]


@mcp.tool()
async def add_labels(
    owner: str, repo: str, issue_number: int, labels: list[str]
) -> dict[str, Any]:
    """Add labels to an issue or pull request (existing labels are kept).

    Disabled in read-only mode; requires write access.
    """
    async with _session(write=True) as gh:
        result = await gh.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
    return {"labels": [lbl.get("name") for lbl in result]}


@mcp.tool()
async def remove_label(
    owner: str, repo: str, issue_number: int, label: str
) -> dict[str, Any]:
    """Remove a single label from an issue or pull request.

    Disabled in read-only mode; requires write access.
    """
    # Label names can contain spaces and slashes (e.g. "good first issue",
    # "type/bug"); percent-encode the segment so the path stays correct.
    async with _session(write=True) as gh:
        result = await gh.delete(
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels/{quote(label, safe='')}"
        )
    remaining = (
        [lbl.get("name") for lbl in result] if isinstance(result, list) else []
    )
    return {"removed": label, "labels": remaining}


@mcp.tool()
async def add_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str]
) -> dict[str, Any]:
    """Assign users to an issue or pull request.

    `assignees` is a list of GitHub logins. Disabled in read-only mode; requires
    write access.
    """
    async with _session(write=True) as gh:
        result = await gh.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/assignees",
            json={"assignees": assignees},
        )
    return {
        "number": result.get("number"),
        "assignees": [a.get("login") for a in result.get("assignees", [])],
    }


@mcp.tool()
async def list_labels(owner: str, repo: str, limit: int = 50) -> list[dict[str, Any]]:
    """List the labels defined in a repository (gh label list).

    Returns each label's name, color (hex, no leading `#`), and description, up to
    `limit` (max 100).
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        labels = await gh.get(
            f"/repos/{owner}/{repo}/labels", params={"per_page": limit}
        )
    return [
        {
            "name": label.get("name"),
            "color": label.get("color"),
            "description": label.get("description"),
        }
        for label in labels
    ]


@mcp.tool()
async def create_label(
    owner: str,
    repo: str,
    name: str,
    color: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a label in a repository (gh label create).

    `color` is a 6-character hex code without the leading `#` (e.g. `d73a4a`); if
    omitted GitHub assigns a default. Disabled in read-only mode; requires write
    access.
    """
    payload: dict[str, Any] = {"name": name}
    if color is not None:
        payload["color"] = color.lstrip("#")
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        label = await gh.post(f"/repos/{owner}/{repo}/labels", json=payload)
    return {
        "name": label.get("name"),
        "color": label.get("color"),
        "description": label.get("description"),
    }


@mcp.tool()
async def update_label(
    owner: str,
    repo: str,
    name: str,
    new_name: str | None = None,
    color: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Edit an existing label (gh label edit).

    `name` selects the label to change; pass `new_name` to rename it, and/or
    `color` (6-char hex, leading `#` optional) and `description` to update those.
    Disabled in read-only mode; requires write access.
    """
    payload: dict[str, Any] = {}
    if new_name is not None:
        payload["new_name"] = new_name
    if color is not None:
        payload["color"] = color.lstrip("#")
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        label = await gh.patch(
            f"/repos/{owner}/{repo}/labels/{quote(name)}", json=payload
        )
    return {
        "name": label.get("name"),
        "color": label.get("color"),
        "description": label.get("description"),
    }


@mcp.tool()
async def delete_label(owner: str, repo: str, name: str) -> dict[str, Any]:
    """Delete a label from a repository (gh label delete).

    Removes the label `name` and unsets it from every issue/PR that had it. This
    cannot be undone. Disabled in read-only mode; requires write access.
    """
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/labels/{quote(name)}")
    return {"deleted": True, "name": name}


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
