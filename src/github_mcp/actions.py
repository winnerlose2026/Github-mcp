"""GitHub Actions: workflow definitions, runs, jobs, logs, dispatch, cancel.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from .client import GitHubError
from .core import _clamp, _session, mcp
from .summaries import _summarize_job, _summarize_workflow_run


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
    limit = _clamp(limit, 50)
    async with _session() as gh:
        result = await gh.get(
            f"/repos/{owner}/{repo}/actions/runs",
            params={"branch": branch, "status": status, "per_page": limit},
        )
    return [_summarize_workflow_run(run) for run in result.get("workflow_runs", [])]


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
    limit = _clamp(limit, 100)
    async with _session() as gh:
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
    async with _session() as gh:
        text = await gh.get_raw(
            f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            accept="application/vnd.github+json",
        )
    truncated = len(text) > max_chars
    clipped = (text[-max_chars:] if tail else text[:max_chars]) if truncated else text
    return {"job_id": job_id, "truncated": truncated, "tail": tail, "logs": clipped}


@mcp.tool()
async def rerun_workflow_run(
    owner: str, repo: str, run_id: int, failed_only: bool = False
) -> dict[str, Any]:
    """Re-run a GitHub Actions workflow run.

    With `failed_only=True`, only the failed jobs are re-run; otherwise the whole
    run is re-run. Get `run_id` from `list_workflow_runs`. Disabled in read-only
    mode; requires a token with write access.
    """
    endpoint = "rerun-failed-jobs" if failed_only else "rerun"
    async with _session(write=True) as gh:
        await gh.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/{endpoint}", json={}
        )
    return {"rerun": True, "run_id": run_id, "failed_only": failed_only}


@mcp.tool()
async def trigger_workflow(
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Manually trigger a workflow_dispatch run.

    `workflow_id` is the workflow file name (e.g. `ci.yml`) or its numeric id.
    `ref` is the branch or tag to run on. `inputs` is an optional map of the
    workflow's declared inputs. The workflow must define an `on: workflow_dispatch`
    trigger. Disabled in read-only mode; requires write access.
    """
    payload: dict[str, Any] = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    async with _session(write=True) as gh:
        await gh.post(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=payload,
        )
    return {"dispatched": True, "workflow_id": workflow_id, "ref": ref}


@mcp.tool()
async def create_scheduled_workflow(
    owner: str,
    repo: str,
    name: str,
    cron: str,
    run: str,
    runs_on: str = "ubuntu-latest",
    branch: str | None = None,
    filename: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Schedule recurring work by committing a cron GitHub Actions workflow.

    This is GitHub's native "do X later / on a schedule": it creates (or updates)
    a workflow file at `.github/workflows/<filename>` that runs `run` (a shell
    script) on the `cron` schedule, and also adds a `workflow_dispatch` trigger
    so you can run it on demand. `cron` is standard 5-field UTC cron
    (e.g. "0 9 * * 1" = 09:00 UTC every Monday).

    IMPORTANT: GitHub only fires `schedule` triggers from a repository's DEFAULT
    branch, so `branch` defaults to it — committing to another branch will run on
    demand but never on the schedule. `filename` defaults to a slug of `name`.
    Disabled in read-only mode; requires write access (and the token needs the
    `workflow` scope to add workflow files).
    """
    if len(cron.split()) != 5:
        raise GitHubError(
            400,
            "CRON",
            f"/repos/{owner}/{repo}",
            f"`cron` must be a 5-field cron expression (got: {cron!r}).",
        )
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "scheduled"
    fname = filename or f"{slug}.yml"
    path = f".github/workflows/{fname}"
    indented_run = "\n".join("          " + line for line in run.splitlines())
    content = (
        f"name: {name}\n"
        "on:\n"
        "  schedule:\n"
        f'    - cron: "{cron}"\n'
        "  workflow_dispatch: {}\n"
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  scheduled:\n"
        f"    runs-on: {runs_on}\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - name: Run scheduled command\n"
        "        run: |\n"
        f"{indented_run}\n"
    )
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    commit_message = message or f"Add scheduled workflow: {name}"
    async with _session(write=True) as gh:
        if branch is None:
            repo_data = await gh.get(f"/repos/{owner}/{repo}")
            branch = repo_data.get("default_branch")
        payload: dict[str, Any] = {
            "message": commit_message,
            "content": encoded,
            "branch": branch,
        }
        # If the workflow file already exists on this branch, update it.
        try:
            existing = await gh.get(
                f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch}
            )
            if isinstance(existing, dict) and existing.get("sha"):
                payload["sha"] = existing.get("sha")
        except GitHubError as exc:
            if exc.status_code != 404:
                raise
        result = await gh.put(f"/repos/{owner}/{repo}/contents/{path}", json=payload)
    commit = result.get("commit", {})
    content_info = result.get("content", {})
    return {
        "path": content_info.get("path", path),
        "branch": branch,
        "cron": cron,
        "runs_on": runs_on,
        "commit_sha": commit.get("sha"),
        "html_url": content_info.get("html_url"),
        "note": "Scheduled runs fire only from the default branch and start "
        "from the next cron tick; use trigger_workflow to run it now.",
    }
