"""Repository administration: collaborators, branch protection, and merges.

Complements :mod:`github_mcp.repos` (which reads collaborators/topics/etc.) with
the write side — adding/removing collaborators and editing branch protection —
plus ``merge_branch`` to merge one branch into another without a pull request.
Write tools are disabled in read-only mode. The package ``__init__`` imports
this module to register them.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .server import _session, mcp

_COLLABORATOR_PERMISSIONS = {"pull", "triage", "push", "maintain", "admin"}


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
