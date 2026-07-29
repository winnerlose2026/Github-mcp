"""Repositories: metadata, branches, trees, collaborators, protection, creation.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .core import _clamp, _session, mcp
from .summaries import _summarize_repo


@mcp.tool()
async def list_repository_collaborators(
    owner: str, repo: str, limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List a repository's collaborators with their permission level.

    Returns up to `limit` (max 100) collaborators. Requires push (or higher)
    access to the repository.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        users = await gh.get(
            f"/repos/{owner}/{repo}/collaborators", params={"per_page": limit, "page": page}
        )
    return [
        {
            "login": u.get("login"),
            "type": u.get("type"),
            "permissions": u.get("permissions"),
            "html_url": u.get("html_url"),
        }
        for u in users
    ]


@mcp.tool()
async def list_repository_languages(owner: str, repo: str) -> dict[str, int]:
    """Get the language breakdown of a repository (bytes of code per language)."""
    async with _session() as gh:
        languages = await gh.get(f"/repos/{owner}/{repo}/languages")
    return languages


@mcp.tool()
async def get_repository_topics(owner: str, repo: str) -> dict[str, Any]:
    """List the topics (tags) set on a repository."""
    async with _session() as gh:
        data = await gh.get(f"/repos/{owner}/{repo}/topics")
    return {"names": data.get("names", [])}


@mcp.tool()
async def replace_repository_topics(
    owner: str, repo: str, topics: list[str]
) -> dict[str, Any]:
    """Replace a repository's topics with `topics` (a write; read-only gated).

    This sets the full topic list (it doesn't append) — pass every topic you
    want to keep. Topic names are lowercase, may include hyphens, and there's a
    limit of 20. Requires a token with write access.
    """
    async with _session(write=True) as gh:
        data = await gh.put(
            f"/repos/{owner}/{repo}/topics", json={"names": topics}
        )
    return {"names": data.get("names", [])}


@mcp.tool()
async def update_repository(
    owner: str,
    repo: str,
    name: str | None = None,
    description: str | None = None,
    homepage: str | None = None,
    private: bool | None = None,
    default_branch: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    """Update a repository's settings (a write; gated by read-only mode).

    Pass only the fields you want to change: `name` (rename), `description`,
    `homepage`, `private`, `default_branch`, or `archived`. Requires a token with
    admin access to the repository.
    """
    payload: dict[str, Any] = {}
    for key, value in (
        ("name", name),
        ("description", description),
        ("homepage", homepage),
        ("private", private),
        ("default_branch", default_branch),
        ("archived", archived),
    ):
        if value is not None:
            payload[key] = value
    async with _session(write=True) as gh:
        updated = await gh.patch(f"/repos/{owner}/{repo}", json=payload)
    return _summarize_repo(updated)


@mcp.tool()
async def create_commit_status(
    owner: str,
    repo: str,
    sha: str,
    state: str,
    target_url: str | None = None,
    description: str | None = None,
    context: str = "default",
) -> dict[str, Any]:
    """Set a commit status on a SHA (a write; gated by read-only mode).

    `state` is one of `error`, `failure`, `pending`, or `success`. `context` is
    the status label (e.g. `ci/my-check`); `target_url` links to details and
    `description` is a short summary. Lets the connector report check-style
    results. Requires a token with write access.
    """
    payload: dict[str, Any] = {"state": state, "context": context}
    if target_url is not None:
        payload["target_url"] = target_url
    if description is not None:
        payload["description"] = description
    async with _session(write=True) as gh:
        status = await gh.post(
            f"/repos/{owner}/{repo}/statuses/{sha}", json=payload
        )
    return {
        "state": status.get("state"),
        "context": status.get("context"),
        "description": status.get("description"),
        "target_url": status.get("target_url"),
    }


_COLLABORATOR_PERMISSIONS = {"pull", "triage", "push", "maintain", "admin"}


@mcp.tool()
async def get_repository(owner: str, repo: str) -> dict[str, Any]:
    """Get metadata for a single repository (description, default branch, stars, etc.)."""
    async with _session() as gh:
        data = await gh.get(f"/repos/{owner}/{repo}")
    return _summarize_repo(data)


@mcp.tool()
async def list_my_repositories(
    affiliation: str = "owner,collaborator,organization_member",
    sort: str = "updated",
    limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List repositories the authenticated user has access to.

    `affiliation` is a comma-separated subset of `owner`, `collaborator`,
    `organization_member`. `sort` is one of `created`, `updated`, `pushed`,
    `full_name`. Returns up to `limit` (max 100) repositories. Use this to
    discover repos the token can reach without knowing their names.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        repos = await gh.get(
            "/user/repos",
            params={"affiliation": affiliation, "sort": sort, "per_page": limit, "page": page},
        )
    return [_summarize_repo(repo) for repo in repos]


@mcp.tool()
async def get_repository_tree(
    owner: str, repo: str, ref: str | None = None, recursive: bool = True
) -> dict[str, Any]:
    """Get the file tree of a repository at a ref.

    `ref` is a branch, tag, or commit SHA (defaults to the repository's default
    branch). With `recursive=True` (default) the entire tree is returned in one
    call — useful for grasping repo layout. `truncated` is True if GitHub capped
    the response (very large repos).
    """
    async with _session() as gh:
        if ref is None:
            repo_data = await gh.get(f"/repos/{owner}/{repo}")
            ref = repo_data.get("default_branch")
            if not ref:
                raise GitHubError(
                    404,
                    "GET",
                    f"/repos/{owner}/{repo}",
                    "Could not determine a default branch; pass `ref` explicitly.",
                )
        commit = await gh.get(f"/repos/{owner}/{repo}/commits/{ref}")
        tree_sha = (commit.get("commit", {}).get("tree") or {}).get("sha")
        if not tree_sha:
            raise GitHubError(
                404,
                "GET",
                f"/repos/{owner}/{repo}/commits/{ref}",
                f"Could not resolve a tree for ref '{ref}'.",
            )
        tree = await gh.get(
            f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params={"recursive": "1" if recursive else None},
        )
    return {
        "ref": ref,
        "sha": tree.get("sha"),
        "truncated": tree.get("truncated"),
        "entries": [
            {"path": e.get("path"), "type": e.get("type"), "size": e.get("size")}
            for e in tree.get("tree", [])
        ],
    }


@mcp.tool()
async def list_branches(owner: str, repo: str, limit: int = 30, page: int = 1) -> list[dict[str, Any]]:
    """List branches in a repository, with the head commit SHA for each.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on."""
    limit = _clamp(limit, 100)
    async with _session() as gh:
        branches = await gh.get(
            f"/repos/{owner}/{repo}/branches", params={"per_page": limit, "page": page}
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
async def create_branch(
    owner: str, repo: str, branch: str, from_ref: str | None = None
) -> dict[str, Any]:
    """Create a new branch in a repository.

    The branch starts at `from_ref` (a branch, tag, or commit SHA); if omitted,
    it starts at the repository's default branch. Disabled in read-only mode;
    requires a token with write access.
    """
    async with _session(write=True) as gh:
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
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
    return {"deleted": True, "branch": branch}


@mcp.tool()
async def create_repository(
    name: str,
    description: str | None = None,
    private: bool = False,
    org: str | None = None,
    auto_init: bool = False,
    homepage: str | None = None,
) -> dict[str, Any]:
    """Create a new repository (gh repo create).

    Creates the repo under the authenticated user, or under `org` if given. Set
    `auto_init=True` to seed an initial commit with a README (so the repo has a
    default branch you can push to immediately). Disabled in read-only mode;
    requires a token with the `repo` scope.
    """
    payload: dict[str, Any] = {"name": name, "private": private}
    if description is not None:
        payload["description"] = description
    if homepage is not None:
        payload["homepage"] = homepage
    if auto_init:
        payload["auto_init"] = True
    path = f"/orgs/{org}/repos" if org else "/user/repos"
    async with _session(write=True) as gh:
        repo = await gh.post(path, json=payload)
    return _summarize_repo(repo)


@mcp.tool()
async def fork_repository(
    owner: str,
    repo: str,
    organization: str | None = None,
    default_branch_only: bool = False,
) -> dict[str, Any]:
    """Fork a repository to your account or an organization (gh repo fork).

    Forks `owner/repo` into the authenticated account, or into `organization` if
    given. Set `default_branch_only=True` to fork just the default branch. The
    fork is created asynchronously by GitHub, so it may take a moment to become
    fully available. Disabled in read-only mode; requires write access.
    """
    payload: dict[str, Any] = {}
    if organization is not None:
        payload["organization"] = organization
    if default_branch_only:
        payload["default_branch_only"] = True
    async with _session(write=True) as gh:
        fork = await gh.post(f"/repos/{owner}/{repo}/forks", json=payload)
    return _summarize_repo(fork)


@mcp.tool()
async def find_reusable_repositories(
    query: str,
    language: str | None = None,
    topic: str | None = None,
    min_stars: int = 0,
    public_only: bool = False,
    include_archived: bool = False,
    limit: int = 10,
    page: int = 1,
) -> dict[str, Any]:
    """Find repositories you could reuse for something you're building.

    Searches every repository the token can see — public repos **and** the
    private/org repos your token has access to — ranked by stars. Set
    `public_only=True` to restrict to public results. Archived repos are
    excluded unless `include_archived=True`. Returns the fields that matter when
    deciding whether to adopt a project: description, stars, language,
    **license**, topics, and last-pushed date (to spot abandoned projects). The
    exact search string is returned as `query` so you can see and refine it.

    PHRASING — get precise results (do this before calling):
    - Translate the user's goal into a *focused* capability phrase: prefer
      "JWT validation middleware" over "auth thing", "S3 multipart upload" over
      "file storage". Concrete nouns beat adjectives.
    - Add `language=` and/or `topic=` whenever you can infer them, and raise
      `min_stars` (e.g. 50–500) to cut noise on broad topics.
    - You may embed GitHub search qualifiers directly in `query` for precision,
      e.g. `in:name,description`, `pushed:>2025-01-01`, `forks:>50`,
      `license:mit`.
    - If the user's need is ambiguous (language? runtime? scale? license?), ask
      one clarifying question before searching rather than guessing.
    - After results come back, if they look off-target, refine the phrasing
      (narrower nouns, add qualifiers) and call again — iterate until precise.

    Returns up to `limit` (max 50) candidates.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    if not query.strip():
        raise GitHubError(
            400,
            "GET",
            "/search/repositories",
            "`query` must be a non-empty search phrase (qualifiers alone are "
            "rejected by GitHub search).",
        )
    limit = _clamp(limit, 50)
    qualifiers = [query.strip()]
    if public_only:
        qualifiers.append("is:public")
    if language:
        qualifiers.append(f"language:{language}")
    if topic:
        qualifiers.append(f"topic:{topic}")
    if min_stars > 0:
        qualifiers.append(f"stars:>={min_stars}")
    if not include_archived:
        qualifiers.append("archived:false")
    q = " ".join(qualifiers)
    async with _session() as gh:
        result = await gh.get(
            "/search/repositories",
            params={"q": q, "sort": "stars", "order": "desc", "per_page": limit, "page": page},
        )
    candidates = [
        {
            "full_name": item.get("full_name"),
            "private": item.get("private"),
            "description": item.get("description"),
            "stars": item.get("stargazers_count"),
            "language": item.get("language"),
            "license": (item.get("license") or {}).get("spdx_id"),
            "topics": item.get("topics", []),
            "open_issues": item.get("open_issues_count"),
            "pushed_at": item.get("pushed_at"),
            "archived": item.get("archived"),
            "html_url": item.get("html_url"),
        }
        for item in result.get("items", [])
    ]
    return {
        "query": q,
        "total_count": result.get("total_count"),
        "results": candidates,
    }


@mcp.tool()
async def add_repository_collaborator(
    owner: str, repo: str, username: str, permission: str = "push"
) -> dict[str, Any]:
    """Add (or invite) a collaborator to a repository (a gated write).

    `permission` is one of `pull`, `triage`, `push` (default), `maintain`,
    `admin`. For an outside user this creates an invitation they must accept; for
    an existing collaborator it updates their permission. Requires admin access.
    """
    if permission not in _COLLABORATOR_PERMISSIONS:
        raise GitHubError(
            422,
            "PUT",
            f"/repos/{owner}/{repo}/collaborators/{username}",
            f"Invalid permission '{permission}'. Must be one of: "
            f"{', '.join(sorted(_COLLABORATOR_PERMISSIONS))}.",
        )
    async with _session(write=True) as gh:
        result = await gh.put(
            f"/repos/{owner}/{repo}/collaborators/{username}",
            json={"permission": permission},
        )
    # 201 returns an invitation; 204 (already a collaborator) returns no body.
    return {
        "added": True,
        "username": username,
        "permission": permission,
        "invitation_id": (result or {}).get("id") if result else None,
    }


@mcp.tool()
async def remove_repository_collaborator(
    owner: str, repo: str, username: str
) -> dict[str, Any]:
    """Remove a collaborator from a repository (a gated write).

    Also cancels a pending invitation for that user. Requires admin access.
    """
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/collaborators/{username}")
    return {"removed": True, "username": username}


@mcp.tool()
async def get_branch_protection(
    owner: str, repo: str, branch: str
) -> dict[str, Any]:
    """Get a branch's protection settings.

    Returns a summary (required status checks, enforce-admins, required review
    count). If the branch isn't protected, returns `{"protected": false}`
    instead of erroring. Requires admin access to read protection.
    """
    async with _session() as gh:
        try:
            data = await gh.get(
                f"/repos/{owner}/{repo}/branches/{branch}/protection"
            )
        except GitHubError as exc:
            if exc.status_code == 404:
                return {"protected": False, "branch": branch}
            raise
    checks = data.get("required_status_checks") or {}
    reviews = data.get("required_pull_request_reviews") or {}
    return {
        "protected": True,
        "branch": branch,
        "required_status_checks_contexts": checks.get("contexts"),
        "strict": checks.get("strict"),
        "enforce_admins": (data.get("enforce_admins") or {}).get("enabled"),
        "required_approving_review_count": reviews.get(
            "required_approving_review_count"
        ),
        "require_code_owner_reviews": reviews.get("require_code_owner_reviews"),
    }


@mcp.tool()
async def update_branch_protection(
    owner: str,
    repo: str,
    branch: str,
    required_status_check_contexts: list[str] | None = None,
    strict: bool = True,
    enforce_admins: bool = False,
    required_approving_review_count: int | None = None,
    require_code_owner_reviews: bool = False,
) -> dict[str, Any]:
    """Set a branch's protection rules (a gated write).

    Pass `required_status_check_contexts` (e.g. `["CI"]`) to require those checks
    (with `strict` requiring the branch be up to date); omit to disable that
    rule. Pass `required_approving_review_count` to require that many PR
    approvals; omit to disable required reviews. `enforce_admins` applies the
    rules to admins too. Requires admin access. (Overwrites existing protection
    with exactly what you specify.)
    """
    body: dict[str, Any] = {
        "required_status_checks": (
            {"strict": strict, "contexts": required_status_check_contexts}
            if required_status_check_contexts is not None
            else None
        ),
        "enforce_admins": enforce_admins,
        "required_pull_request_reviews": (
            {
                "required_approving_review_count": required_approving_review_count,
                "require_code_owner_reviews": require_code_owner_reviews,
            }
            if required_approving_review_count is not None
            else None
        ),
        "restrictions": None,
    }
    async with _session(write=True) as gh:
        await gh.put(
            f"/repos/{owner}/{repo}/branches/{branch}/protection", json=body
        )
    return {"updated": True, "branch": branch}


@mcp.tool()
async def merge_branch(
    owner: str,
    repo: str,
    base: str,
    head: str,
    commit_message: str | None = None,
) -> dict[str, Any]:
    """Merge one branch into another without a pull request (a gated write).

    Merges `head` (a branch name or SHA) into the `base` branch, creating a
    merge commit. Returns the new commit, or `{"merged": false}` if `base` is
    already up to date. A merge conflict surfaces as a 409 error.
    """
    payload: dict[str, Any] = {"base": base, "head": head}
    if commit_message is not None:
        payload["commit_message"] = commit_message
    async with _session(write=True) as gh:
        result = await gh.post(f"/repos/{owner}/{repo}/merges", json=payload)
    if not result:  # 204 No Content -> nothing to merge
        return {"merged": False, "base": base, "head": head}
    return {
        "merged": True,
        "base": base,
        "head": head,
        "sha": result.get("sha"),
        "html_url": result.get("html_url"),
    }
