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
