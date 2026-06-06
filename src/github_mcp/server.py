"""The GitHub MCP connector server.

Defines the FastMCP server and the GitHub tools it exposes. Run it with::

    python -m github_mcp            # stdio transport (Claude Desktop/Code)
    python -m github_mcp --http     # streamable HTTP transport

Write tools (creating issues, commenting) are disabled when the environment
variable ``GITHUB_MCP_READ_ONLY`` is truthy.
"""

from __future__ import annotations

import base64
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import GitHubClient, GitHubError
from .config import Config

config = Config.from_env()

INSTRUCTIONS = """\
This server connects Claude to GitHub via the REST API.

Use it to look up repositories, read files and commit history, triage issues,
and review pull requests. Always pass `owner` and `repo` separately (for the
repo `octocat/hello-world`, owner is `octocat` and repo is `hello-world`).

For free-text discovery use the `search_*` tools, which accept GitHub search
qualifiers (e.g. `repo:owner/name`, `is:open`, `label:bug`, `language:python`).
"""

mcp = FastMCP("github", instructions=INSTRUCTIONS)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require_token() -> None:
    if not config.token:
        raise GitHubError(
            401,
            "AUTH",
            config.api_url,
            "No GitHub token configured. Set GITHUB_TOKEN (or "
            "GITHUB_PERSONAL_ACCESS_TOKEN) in the connector environment.",
        )


def _require_write() -> None:
    if config.read_only:
        raise GitHubError(
            403,
            "WRITE",
            config.api_url,
            "This connector is running in read-only mode "
            "(GITHUB_MCP_READ_ONLY is set); write operations are disabled.",
        )


def _summarize_repo(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "description": repo.get("description"),
        "private": repo.get("private"),
        "fork": repo.get("fork"),
        "default_branch": repo.get("default_branch"),
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues": repo.get("open_issues_count"),
        "html_url": repo.get("html_url"),
        "updated_at": repo.get("updated_at"),
    }


def _summarize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "user": (issue.get("user") or {}).get("login"),
        "labels": [label.get("name") for label in issue.get("labels", [])],
        "comments": issue.get("comments"),
        "is_pull_request": "pull_request" in issue,
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "html_url": issue.get("html_url"),
    }


def _summarize_pull(pull: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pull.get("number"),
        "title": pull.get("title"),
        "state": pull.get("state"),
        "draft": pull.get("draft"),
        "user": (pull.get("user") or {}).get("login"),
        "head": (pull.get("head") or {}).get("ref"),
        "base": (pull.get("base") or {}).get("ref"),
        "merged": pull.get("merged"),
        "mergeable": pull.get("mergeable"),
        "comments": pull.get("comments"),
        "review_comments": pull.get("review_comments"),
        "changed_files": pull.get("changed_files"),
        "additions": pull.get("additions"),
        "deletions": pull.get("deletions"),
        "created_at": pull.get("created_at"),
        "html_url": pull.get("html_url"),
    }


def _summarize_commit(commit: dict[str, Any]) -> dict[str, Any]:
    detail = commit.get("commit", {})
    author = detail.get("author", {})
    return {
        "sha": commit.get("sha"),
        "message": detail.get("message"),
        "author": author.get("name"),
        "date": author.get("date"),
        "html_url": commit.get("html_url"),
    }


def _summarize_file(file: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": file.get("filename"),
        "status": file.get("status"),
        "additions": file.get("additions"),
        "deletions": file.get("deletions"),
        "changes": file.get("changes"),
        "previous_filename": file.get("previous_filename"),
    }


def _summarize_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "display_title": run.get("display_title"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "run_number": run.get("run_number"),
        "created_at": run.get("created_at"),
        "html_url": run.get("html_url"),
    }


def _summarize_release(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_name": release.get("tag_name"),
        "name": release.get("name"),
        "draft": release.get("draft"),
        "prerelease": release.get("prerelease"),
        "published_at": release.get("published_at"),
        "author": (release.get("author") or {}).get("login"),
        "html_url": release.get("html_url"),
    }


def _summarize_job(job: dict[str, Any]) -> dict[str, Any]:
    steps = job.get("steps") or []
    failed_steps = [
        s.get("name") for s in steps if s.get("conclusion") == "failure"
    ]
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "status": job.get("status"),
        "conclusion": job.get("conclusion"),
        "failed_steps": failed_steps,
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "html_url": job.get("html_url"),
    }


def _summarize_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": review.get("id"),
        "user": (review.get("user") or {}).get("login"),
        "state": review.get("state"),
        "body": review.get("body"),
        "submitted_at": review.get("submitted_at"),
        "html_url": review.get("html_url"),
    }


def _summarize_secret_alert(alert: dict[str, Any]) -> dict[str, Any]:
    # Deliberately omit the raw `secret` value GitHub may include.
    return {
        "number": alert.get("number"),
        "state": alert.get("state"),
        "secret_type": alert.get("secret_type"),
        "secret_type_display_name": alert.get("secret_type_display_name"),
        "resolution": alert.get("resolution"),
        "created_at": alert.get("created_at"),
        "html_url": alert.get("html_url"),
    }


# ---------------------------------------------------------------------------
# read tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_authenticated_user() -> dict[str, Any]:
    """Return the GitHub account the connector's token authenticates as.

    Useful as a connection/health check and to confirm which identity and
    permissions the connector is operating with.
    """
    _require_token()
    async with GitHubClient(config) as gh:
        user = await gh.get("/user")
    return {
        "login": user.get("login"),
        "name": user.get("name"),
        "type": user.get("type"),
        "public_repos": user.get("public_repos"),
        "html_url": user.get("html_url"),
    }


@mcp.tool()
async def search_repositories(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search GitHub for repositories matching a query.

    `query` accepts GitHub search syntax, e.g. `language:python topic:mcp` or
    `org:anthropics stars:>100`. Returns up to `limit` (max 50) repositories.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        result = await gh.get(
            "/search/repositories", params={"q": query, "per_page": limit}
        )
    return [_summarize_repo(item) for item in result.get("items", [])]


@mcp.tool()
async def get_repository(owner: str, repo: str) -> dict[str, Any]:
    """Get metadata for a single repository (description, default branch, stars, etc.)."""
    _require_token()
    async with GitHubClient(config) as gh:
        data = await gh.get(f"/repos/{owner}/{repo}")
    return _summarize_repo(data)


@mcp.tool()
async def list_branches(owner: str, repo: str, limit: int = 30) -> list[dict[str, Any]]:
    """List branches in a repository, with the head commit SHA for each."""
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        branches = await gh.get(
            f"/repos/{owner}/{repo}/branches", params={"per_page": limit}
        )
    return [
        {
            "name": branch.get("name"),
            "sha": (branch.get("commit") or {}).get("sha"),
            "protected": branch.get("protected"),
        }
        for branch in branches
    ]


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
    _require_token()
    async with GitHubClient(config) as gh:
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
async def list_commits(
    owner: str,
    repo: str,
    sha: str | None = None,
    path: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent commits on a repository.

    Optionally narrow to a branch/SHA via `sha` or to commits touching a single
    file via `path`. Returns up to `limit` (max 50) commits.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        commits = await gh.get(
            f"/repos/{owner}/{repo}/commits",
            params={"sha": sha, "path": path, "per_page": limit},
        )
    return [_summarize_commit(commit) for commit in commits]


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
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        issues = await gh.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "labels": labels, "per_page": limit},
        )
    return [_summarize_issue(issue) for issue in issues]


@mcp.tool()
async def get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    """Get a single issue including its full body text."""
    _require_token()
    async with GitHubClient(config) as gh:
        issue = await gh.get(f"/repos/{owner}/{repo}/issues/{issue_number}")
    summary = _summarize_issue(issue)
    summary["body"] = issue.get("body")
    return summary


@mcp.tool()
async def list_pull_requests(
    owner: str, repo: str, state: str = "open", limit: int = 20
) -> list[dict[str, Any]]:
    """List pull requests in a repository.

    `state` is one of `open`, `closed`, or `all`. Returns up to `limit`
    (max 50) pull requests.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        pulls = await gh.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": limit},
        )
    return [_summarize_pull(pull) for pull in pulls]


@mcp.tool()
async def get_pull_request(
    owner: str, repo: str, pull_number: int
) -> dict[str, Any]:
    """Get a single pull request including its body and merge status."""
    _require_token()
    async with GitHubClient(config) as gh:
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
    _require_token()
    async with GitHubClient(config) as gh:
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
async def search_issues(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search issues and pull requests across GitHub using search qualifiers.

    Example queries: `repo:octocat/hello-world is:open label:bug`,
    `is:pr author:octocat is:merged`. Returns up to `limit` (max 50) results.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        result = await gh.get(
            "/search/issues",
            params={"q": query, "per_page": limit},
        )
    return [_summarize_issue(item) for item in result.get("items", [])]


@mcp.tool()
async def search_code(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search for code across GitHub.

    Example: `addClass in:file language:js repo:jquery/jquery`. A `repo:`,
    `org:`, or `user:` qualifier is usually required by GitHub's code search.
    Returns up to `limit` (max 50) matching files.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        result = await gh.get(
            "/search/code",
            params={"q": query, "per_page": limit},
        )
    return [
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "repository": (item.get("repository") or {}).get("full_name"),
            "html_url": item.get("html_url"),
        }
        for item in result.get("items", [])
    ]


@mcp.tool()
async def list_my_repositories(
    affiliation: str = "owner,collaborator,organization_member",
    sort: str = "updated",
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List repositories the authenticated user has access to.

    `affiliation` is a comma-separated subset of `owner`, `collaborator`,
    `organization_member`. `sort` is one of `created`, `updated`, `pushed`,
    `full_name`. Returns up to `limit` (max 100) repositories. Use this to
    discover repos the token can reach without knowing their names.
    """
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        repos = await gh.get(
            "/user/repos",
            params={"affiliation": affiliation, "sort": sort, "per_page": limit},
        )
    return [_summarize_repo(repo) for repo in repos]


@mcp.tool()
async def get_commit(owner: str, repo: str, ref: str) -> dict[str, Any]:
    """Get a single commit with its stats and changed files.

    `ref` is a commit SHA, branch, or tag. Returns the commit metadata plus
    aggregate additions/deletions and a per-file summary (no patch text).
    """
    _require_token()
    async with GitHubClient(config) as gh:
        commit = await gh.get(f"/repos/{owner}/{repo}/commits/{ref}")
    summary = _summarize_commit(commit)
    summary["stats"] = commit.get("stats")
    summary["files"] = [_summarize_file(f) for f in commit.get("files", [])]
    return summary


@mcp.tool()
async def compare_commits(
    owner: str, repo: str, base: str, head: str
) -> dict[str, Any]:
    """Compare two commits, branches, or tags.

    Returns how `head` relates to `base` (`ahead_by`/`behind_by`), the commits
    in between, and the files changed. Useful for "what's on this branch that
    isn't on main" or reviewing a range.
    """
    _require_token()
    async with GitHubClient(config) as gh:
        result = await gh.get(f"/repos/{owner}/{repo}/compare/{base}...{head}")
    return {
        "status": result.get("status"),
        "ahead_by": result.get("ahead_by"),
        "behind_by": result.get("behind_by"),
        "total_commits": result.get("total_commits"),
        "commits": [_summarize_commit(c) for c in result.get("commits", [])],
        "files": [_summarize_file(f) for f in result.get("files", [])],
        "html_url": result.get("html_url"),
    }


@mcp.tool()
async def list_pull_request_files(
    owner: str, repo: str, pull_number: int, limit: int = 50
) -> list[dict[str, Any]]:
    """List the files changed in a pull request.

    Returns each file's path, status (added/modified/removed/renamed), and
    line counts. Returns up to `limit` (max 100) files.
    """
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        files = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/files",
            params={"per_page": limit},
        )
    return [_summarize_file(f) for f in files]


@mcp.tool()
async def list_workflow_runs(
    owner: str,
    repo: str,
    branch: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent GitHub Actions workflow runs for a repository.

    Optionally filter by `branch` or by `status` (e.g. `completed`,
    `in_progress`, `queued`, `failure`, `success`). Returns up to `limit`
    (max 50) runs, newest first.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        result = await gh.get(
            f"/repos/{owner}/{repo}/actions/runs",
            params={"branch": branch, "status": status, "per_page": limit},
        )
    return [_summarize_workflow_run(run) for run in result.get("workflow_runs", [])]


@mcp.tool()
async def list_releases(
    owner: str, repo: str, limit: int = 20
) -> list[dict[str, Any]]:
    """List releases for a repository, newest first.

    Returns up to `limit` (max 50) releases with tag, name, draft/prerelease
    flags, and publish date.
    """
    _require_token()
    limit = max(1, min(limit, 50))
    async with GitHubClient(config) as gh:
        releases = await gh.get(
            f"/repos/{owner}/{repo}/releases", params={"per_page": limit}
        )
    return [_summarize_release(r) for r in releases]


@mcp.tool()
async def list_workflow_run_jobs(
    owner: str, repo: str, run_id: int, filter: str = "latest", limit: int = 30
) -> list[dict[str, Any]]:
    """List the jobs of a GitHub Actions workflow run.

    Use this to see which job(s) in a run failed (check `conclusion` and
    `failed_steps`) and to get each job's `id` for `get_job_logs`. `filter` is
    `latest` (default) or `all` (include earlier attempts). Returns up to `limit`
    (max 100) jobs.
    """
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        result = await gh.get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            params={"filter": filter, "per_page": limit},
        )
    return [_summarize_job(j) for j in result.get("jobs", [])]


@mcp.tool()
async def get_job_logs(
    owner: str, repo: str, job_id: int, max_chars: int = 20000, tail: bool = True
) -> dict[str, Any]:
    """Get the plain-text logs for a single GitHub Actions job.

    Get `job_id` from `list_workflow_run_jobs`. Logs are truncated to
    `max_chars`; with `tail=True` (default) the END of the log is returned
    (where failures usually are), otherwise the beginning. `truncated` indicates
    whether anything was cut.
    """
    _require_token()
    async with GitHubClient(config) as gh:
        text = await gh.get_raw(
            f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            accept="application/vnd.github+json",
        )
    truncated = len(text) > max_chars
    clipped = (text[-max_chars:] if tail else text[:max_chars]) if truncated else text
    return {"job_id": job_id, "truncated": truncated, "tail": tail, "logs": clipped}


@mcp.tool()
async def list_pull_request_reviews(
    owner: str, repo: str, pull_number: int, limit: int = 30
) -> list[dict[str, Any]]:
    """List the reviews submitted on a pull request.

    Returns each review's author, `state` (e.g. `APPROVED`, `CHANGES_REQUESTED`,
    `COMMENTED`, `DISMISSED`), and body. Returns up to `limit` (max 100) reviews.
    """
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        reviews = await gh.get(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            params={"per_page": limit},
        )
    return [_summarize_review(r) for r in reviews]


@mcp.tool()
async def list_secret_scanning_alerts(
    owner: str, repo: str, state: str = "open", limit: int = 30
) -> list[dict[str, Any]]:
    """List secret-scanning alerts for a repository (the Security tab).

    `state` is `open` (default), `resolved`, or `all`. The raw secret value is
    never returned — only the type, state, and resolution. Requires a token with
    access to security alerts (repo admin / `security_events`); GitHub returns
    403/404 otherwise. Returns up to `limit` (max 100) alerts.
    """
    _require_token()
    limit = max(1, min(limit, 100))
    async with GitHubClient(config) as gh:
        alerts = await gh.get(
            f"/repos/{owner}/{repo}/secret-scanning/alerts",
            params={"state": state, "per_page": limit},
        )
    return [_summarize_secret_alert(a) for a in alerts]


# ---------------------------------------------------------------------------
# write tools (disabled in read-only mode)
# ---------------------------------------------------------------------------


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
    _require_token()
    _require_write()
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    async with GitHubClient(config) as gh:
        issue = await gh.post(f"/repos/{owner}/{repo}/issues", json=payload)
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
    _require_token()
    _require_write()
    async with GitHubClient(config) as gh:
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
    _require_token()
    _require_write()
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
    async with GitHubClient(config) as gh:
        issue = await gh.patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}", json=payload
        )
    summary = _summarize_issue(issue)
    summary["body"] = issue.get("body")
    return summary


@mcp.tool()
async def create_branch(
    owner: str, repo: str, branch: str, from_ref: str | None = None
) -> dict[str, Any]:
    """Create a new branch in a repository.

    The branch starts at `from_ref` (a branch, tag, or commit SHA); if omitted,
    it starts at the repository's default branch. Disabled in read-only mode;
    requires a token with write access.
    """
    _require_token()
    _require_write()
    async with GitHubClient(config) as gh:
        if from_ref is None:
            repo_data = await gh.get(f"/repos/{owner}/{repo}")
            from_ref = repo_data.get("default_branch")
        # Resolve the starting ref to a concrete commit SHA.
        base = await gh.get(f"/repos/{owner}/{repo}/commits/{from_ref}")
        sha = base.get("sha")
        ref = await gh.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
    return {
        "ref": ref.get("ref"),
        "sha": (ref.get("object") or {}).get("sha", sha),
        "from_ref": from_ref,
    }


@mcp.tool()
async def delete_branch(owner: str, repo: str, branch: str) -> dict[str, Any]:
    """Delete a branch from a repository.

    `branch` is the branch name (e.g. `feature-x`, not `refs/heads/feature-x`).
    This permanently removes the ref; it cannot delete the repository's default
    branch (GitHub rejects that). Disabled in read-only mode; requires a token
    with write access.
    """
    _require_token()
    _require_write()
    async with GitHubClient(config) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
    return {"deleted": True, "branch": branch}


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
    _require_token()
    _require_write()
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {"message": message, "content": encoded}
    if branch is not None:
        payload["branch"] = branch
    async with GitHubClient(config) as gh:
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
    _require_token()
    _require_write()
    payload: dict[str, Any] = {
        "title": title,
        "head": head,
        "base": base,
        "draft": draft,
        "maintainer_can_modify": maintainer_can_modify,
    }
    if body is not None:
        payload["body"] = body
    async with GitHubClient(config) as gh:
        pull = await gh.post(f"/repos/{owner}/{repo}/pulls", json=payload)
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
    _require_token()
    _require_write()
    payload: dict[str, Any] = {"merge_method": merge_method}
    if commit_title is not None:
        payload["commit_title"] = commit_title
    if commit_message is not None:
        payload["commit_message"] = commit_message
    async with GitHubClient(config) as gh:
        result = await gh.put(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", json=payload
        )
    return {
        "merged": result.get("merged"),
        "sha": result.get("sha"),
        "message": result.get("message"),
    }


@mcp.tool()
async def rerun_workflow_run(
    owner: str, repo: str, run_id: int, failed_only: bool = False
) -> dict[str, Any]:
    """Re-run a GitHub Actions workflow run.

    With `failed_only=True`, only the failed jobs are re-run; otherwise the whole
    run is re-run. Get `run_id` from `list_workflow_runs`. Disabled in read-only
    mode; requires a token with write access.
    """
    _require_token()
    _require_write()
    endpoint = "rerun-failed-jobs" if failed_only else "rerun"
    async with GitHubClient(config) as gh:
        await gh.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/{endpoint}", json={}
        )
    return {"rerun": True, "run_id": run_id, "failed_only": failed_only}


@mcp.tool()
async def create_release(
    owner: str,
    repo: str,
    tag_name: str,
    target_commitish: str | None = None,
    name: str | None = None,
    body: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
    generate_release_notes: bool = False,
) -> dict[str, Any]:
    """Create a release, creating its git tag if it doesn't already exist.

    `tag_name` is the tag (e.g. `v1.2.0`). If that tag doesn't exist yet, it's
    created pointing at `target_commitish` (a branch, tag, or commit SHA;
    defaults to the repository's default branch). `name` is the release title,
    `body` its notes. Set `generate_release_notes=True` to have GitHub
    auto-generate notes from merged PRs (appended to `body` if both are given),
    `draft=True` to save without publishing, or `prerelease=True` to mark it a
    pre-release.

    Publishing a (non-draft) release fires GitHub's `release: published` event —
    handy for triggering release workflows. Disabled in read-only mode; requires
    a token with write access.
    """
    _require_token()
    _require_write()
    payload: dict[str, Any] = {
        "tag_name": tag_name,
        "draft": draft,
        "prerelease": prerelease,
        "generate_release_notes": generate_release_notes,
    }
    if target_commitish is not None:
        payload["target_commitish"] = target_commitish
    if name is not None:
        payload["name"] = name
    if body is not None:
        payload["body"] = body
    async with GitHubClient(config) as gh:
        release = await gh.post(f"/repos/{owner}/{repo}/releases", json=payload)
    summary = _summarize_release(release)
    summary["id"] = release.get("id")
    summary["body"] = release.get("body")
    return summary


def main(argv: list[str] | None = None) -> None:
    """Console entry point. Selects the transport from CLI args/env."""
    import argparse

    parser = argparse.ArgumentParser(prog="github-mcp", description=__doc__)
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over streamable HTTP instead of stdio.",
    )
    args = parser.parse_args(argv)
    mcp.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
