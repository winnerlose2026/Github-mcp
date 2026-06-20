"""Deployment-gate tools for GitHub Actions environments.

When a workflow job targets an environment with required reviewers (e.g. a
`pypi` environment that gates publishing), the run pauses until a reviewer
approves. These tools let you see what's waiting and approve or reject it
without leaving the chat. ``review_deployment`` is a write (disabled in
read-only mode). The package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .server import _session, mcp

_REVIEW_STATES = {"approved", "rejected"}


@mcp.tool()
async def list_pending_deployments(
    owner: str, repo: str, run_id: int
) -> list[dict[str, Any]]:
    """List the environments a workflow run is waiting on for approval.

    For a run parked on an environment protection rule, returns each pending
    environment with its id, name, wait timer, and whether the current token
    may approve it. Feed an `environment_id` from here into `review_deployment`.
    """
    async with _session() as gh:
        pending = await gh.get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments"
        )
    return [
        {
            "environment": (p.get("environment") or {}).get("name"),
            "environment_id": (p.get("environment") or {}).get("id"),
            "wait_timer": p.get("wait_timer"),
            "current_user_can_approve": p.get("current_user_can_approve"),
            "reviewers": [
                (r.get("reviewer") or {}).get("login")
                or (r.get("reviewer") or {}).get("name")
                for r in p.get("reviewers", [])
            ],
        }
        for p in pending
    ]


@mcp.tool()
async def review_deployment(
    owner: str,
    repo: str,
    run_id: int,
    environment_ids: list[int],
    state: str,
    comment: str = "",
) -> dict[str, Any]:
    """Approve or reject pending deployments for a workflow run (a gated write).

    `state` must be `approved` or `rejected`. `environment_ids` are the ids from
    `list_pending_deployments`. `comment` is an optional note (GitHub requires a
    non-empty comment when rejecting). Approving lets a gated job (e.g. a PyPI
    publish) proceed. Requires a token whose user is a configured reviewer for
    the environment.
    """
    if state not in _REVIEW_STATES:
        raise GitHubError(
            422,
            "POST",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments",
            f"Invalid state '{state}'. Must be one of: approved, rejected.",
        )
    async with _session(write=True) as gh:
        await gh.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments",
            json={
                "environment_ids": environment_ids,
                "state": state,
                "comment": comment,
            },
        )
    return {
        "reviewed": True,
        "state": state,
        "environment_ids": environment_ids,
        "comment": comment,
    }
