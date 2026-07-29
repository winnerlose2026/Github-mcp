"""Pull requests: listing, diffs, files, reviews, comments, and write actions.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .core import _clamp, _session, mcp
from .summaries import _summarize_comment, _summarize_file, _summarize_pull, _summarize_review


@mcp.tool()
async def list_pull_requests(
    owner: str, repo: str, state: str = "open", limit: int = 20,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List pull requests in a repository.

    `state` is one of `open`, `closed`, or `all`. Returns up to `limit`
    (max 50) pull requests.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 50)
    async with _session() as gh:
        pulls = await gh.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": limit, "page": page},
        )
    return [_summarize_pull(pull) for pull in pulls]


@mcp.tool()
async def get_pull_request(
    owner: str, repo: str, pull_number: int
) -> dict[str, Any]:
    """Get a single pull request including its body and merge status."""
    async with _session() as gh:
        pull = await gh.get(f"/repos/{owner}/{repo}/pulls/{pull_number}")
    summary = _summarize_pull(pull)
    summary["body"] = pull.get("body")
    return summary


@mcp.tool()
async def get_pull_request_diff(
    owner: str, repo: str, pull_number: int, max_chars: int = 20000
) -> dict[str, Any]:
    """Get the unified diff for a pull request.

    The diff is truncated to `max_chars` characters to stay within context
    limits; `truncated` indicates whether anything was cut off.
    """
    async with _session() as gh:
        diff = await gh.get_raw(
            f"/repos/{owner}/{repo}/pulls/{pull_number}",
            accept="application/vnd.github.diff",
        )
    truncated = len(diff) > max_chars
    return {
        "pull_number": pull_number,
        "truncated": truncated,
        "diff": diff[:max_chars],
    }


@mcp.tool()
async def list_pull_request_files(
    owner: str, repo: str, pull_number: int, limit: int = 50,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List the files changed in a pull request.

    Returns each file's path, status (added/modified/removed/renamed), and
    line counts. Returns up to `limit` (max 100) files.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        files = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/files",
            params={"per_page": limit, "page": page},
        )
    return [_summarize_file(f) for f in files]


@mcp.tool()
async def list_pull_request_reviews(
    owner: str, repo: str, pull_number: int, limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List the reviews submitted on a pull request.

    Returns each review's author, `state` (e.g. `APPROVED`, `CHANGES_REQUESTED`,
    `COMMENTED`, `DISMISSED`), and body. Returns up to `limit` (max 100) reviews.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        reviews = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            params={"per_page": limit, "page": page},
        )
    return [_summarize_review(r) for r in reviews]


@mcp.tool()
async def list_pull_request_review_comments(
    owner: str, repo: str, pull_number: int, limit: int = 50,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List inline code-review comments on a pull request.

    These are comments anchored to specific files/lines in the diff (each
    includes `path` and `line`). Returns up to `limit` (max 100) comments.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        comments = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/comments",
            params={"per_page": limit, "page": page},
        )
    return [_summarize_comment(c) for c in comments]


@mcp.tool()
async def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str | None = None,
    draft: bool = False,
    maintainer_can_modify: bool = True,
) -> dict[str, Any]:
    """Open a new pull request.

    `head` is the branch with your changes (for a cross-fork PR use
    `owner:branch`); `base` is the branch you want to merge into (e.g. `main`).
    Set `draft=True` to open it as a draft. Disabled in read-only mode; requires
    a token with write access to the repository.
    """
    payload: dict[str, Any] = {
        "title": title,
        "head": head,
        "base": base,
        "draft": draft,
        "maintainer_can_modify": maintainer_can_modify,
    }
    if body is not None:
        payload["body"] = body
    async with _session(write=True) as gh:
        pull = await gh.post(f"/repos/{owner}/{repo}/pulls", json=payload)
    summary = _summarize_pull(pull)
    summary["body"] = pull.get("body")
    return summary


@mcp.tool()
async def update_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    base: str | None = None,
) -> dict[str, Any]:
    """Edit a pull request: change its title, body, base branch, or state.

    Pass `state` as `closed` to close or `open` to reopen. `base` retargets the
    PR onto a different base branch. Only provided fields change. (Note: toggling
    draft↔ready isn't supported by the REST API.) Disabled in read-only mode;
    requires write access.
    """
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if base is not None:
        payload["base"] = base
    if not payload:
        raise GitHubError(
            400,
            "PATCH",
            f"/repos/{owner}/{repo}/pulls/{pull_number}",
            "Nothing to update: provide at least one of title, body, state, base.",
        )
    async with _session(write=True) as gh:
        pull = await gh.patch(
            f"/repos/{owner}/{repo}/pulls/{pull_number}", json=payload
        )
    summary = _summarize_pull(pull)
    summary["body"] = pull.get("body")
    return summary


@mcp.tool()
async def merge_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    merge_method: str = "merge",
    commit_title: str | None = None,
    commit_message: str | None = None,
) -> dict[str, Any]:
    """Merge a pull request.

    `merge_method` is one of `merge` (merge commit), `squash`, or `rebase`.
    `commit_title`/`commit_message` optionally override the merge commit text
    (ignored for `rebase`). Fails if the PR isn't mergeable (conflicts, failing
    required checks, or branch protection). Disabled in read-only mode; requires
    a token with write access.
    """
    payload: dict[str, Any] = {"merge_method": merge_method}
    if commit_title is not None:
        payload["commit_title"] = commit_title
    if commit_message is not None:
        payload["commit_message"] = commit_message
    async with _session(write=True) as gh:
        result = await gh.put(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", json=payload
        )
    return {
        "merged": result.get("merged"),
        "sha": result.get("sha"),
        "message": result.get("message"),
    }


@mcp.tool()
async def submit_pull_request_review(
    owner: str,
    repo: str,
    pull_number: int,
    event: str,
    body: str | None = None,
) -> dict[str, Any]:
    """Submit a review on a pull request.

    `event` is `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`. `body` is the review
    summary text (required by GitHub for `REQUEST_CHANGES` and `COMMENT`).
    Disabled in read-only mode; requires write access.
    """
    if event in {"REQUEST_CHANGES", "COMMENT"} and not body:
        raise GitHubError(
            400,
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            f"`body` is required when event is {event}.",
        )
    payload: dict[str, Any] = {"event": event}
    if body is not None:
        payload["body"] = body
    async with _session(write=True) as gh:
        review = await gh.post(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews", json=payload
        )
    return _summarize_review(review)


@mcp.tool()
async def add_pull_request_review_comment(
    owner: str,
    repo: str,
    pull_number: int,
    body: str,
    commit_id: str,
    path: str,
    line: int,
    side: str = "RIGHT",
) -> dict[str, Any]:
    """Add an inline review comment on a specific line of a pull request's diff.

    `commit_id` is the SHA being commented on (typically the PR head), `path`
    the file, `line` the line number in the file, and `side` is `RIGHT` (the new
    version, default) or `LEFT` (the old version). Disabled in read-only mode;
    requires write access.
    """
    payload = {
        "body": body,
        "commit_id": commit_id,
        "path": path,
        "line": line,
        "side": side,
    }
    async with _session(write=True) as gh:
        comment = await gh.post(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/comments", json=payload
        )
    return _summarize_comment(comment)


@mcp.tool()
async def request_pull_request_reviewers(
    owner: str,
    repo: str,
    pull_number: int,
    reviewers: list[str] | None = None,
    team_reviewers: list[str] | None = None,
) -> dict[str, Any]:
    """Request reviews on a pull request (gh pr edit --add-reviewer).

    `reviewers` is a list of usernames; `team_reviewers` a list of team slugs.
    At least one of the two must be provided. Disabled in read-only mode;
    requires write access.
    """
    if not reviewers and not team_reviewers:
        raise GitHubError(
            400,
            "REVIEWERS",
            f"/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
            "Provide at least one of `reviewers` or `team_reviewers`.",
        )
    payload: dict[str, Any] = {}
    if reviewers:
        payload["reviewers"] = reviewers
    if team_reviewers:
        payload["team_reviewers"] = team_reviewers
    async with _session(write=True) as gh:
        pull = await gh.post(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
            json=payload,
        )
    return {
        "number": pull.get("number"),
        "requested_reviewers": [
            r.get("login") for r in pull.get("requested_reviewers", [])
        ],
        "requested_teams": [
            t.get("slug") for t in pull.get("requested_teams", [])
        ],
    }


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
