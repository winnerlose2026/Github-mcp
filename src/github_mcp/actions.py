"""Additional GitHub Actions tools.

Complements the workflow-run tools in :mod:`github_mcp.server`
(``list_workflow_runs``, ``rerun_workflow_run``, ``trigger_workflow``). This
module adds ``list_workflows`` (the workflow *definitions* in a repo) and
``cancel_workflow_run`` (the counterpart to re-running). They register on the
shared FastMCP instance and reuse the server's auth/session, so they honor the
same token and read-only policy; the package ``__init__`` imports this module
for the side effect of registering them.
"""

from __future__ import annotations

from typing import Any

from .server import _clamp, _session, mcp


@mcp.tool()
async def list_workflows(owner: str, repo: str, limit: int = 30) -> list[dict[str, Any]]:
    """List the workflow definitions in a repository (gh workflow list).

    These are the workflows under `.github/workflows` (the `id`/`name` you'd
    dispatch with `trigger_workflow`), not individual runs. Returns up to `limit`
    (max 100) workflows with their id, name, path, and state.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        result = await gh.get(
            f"/repos/{owner}/{repo}/actions/workflows", params={"per_page": limit}
        )
    return [
        {
            "id": wf.get("id"),
            "name": wf.get("name"),
            "path": wf.get("path"),
            "state": wf.get("state"),
            "html_url": wf.get("html_url"),
        }
        for wf in result.get("workflows", [])
    ]


@mcp.tool()
async def cancel_workflow_run(
    owner: str, repo: str, run_id: int
) -> dict[str, Any]:
    """Cancel an in-progress workflow run (a write; gated by read-only mode).

    `run_id` is the numeric run id (from `list_workflow_runs`). GitHub cancels
    the run asynchronously, so this returns immediately after the request is
    accepted. Requires a token with write access.
    """
    async with _session(write=True) as gh:
        await gh.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel", json={}
        )
    return {"cancelled": True, "run_id": run_id}
