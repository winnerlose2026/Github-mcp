"""Tests for github_mcp.actions."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import actions, core
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the shared session at a mocked GitHub API.

    Tools call `core._session`, which reads `core.config` and
    `core.GitHubClient`, so those are what we patch.
    """
    cfg = Config(
        token=token,
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(core, "config", cfg)
    monkeypatch.setattr(
        core, "GitHubClient", lambda c: GitHubClient(c, transport=transport)
    )


async def test_list_workflows(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/workflows"
        return httpx.Response(200, json={"workflows": [
            {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml",
             "state": "active", "html_url": "u"}]})

    install_mock(monkeypatch, handler)
    result = await actions.list_workflows("o", "r")
    assert result[0]["id"] == 1
    assert result[0]["path"].endswith("ci.yml")


async def test_cancel_workflow_run(monkeypatch):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/actions/runs/55/cancel"
        return httpx.Response(202, json={})

    install_mock(monkeypatch, handler)
    result = await actions.cancel_workflow_run("o", "r", 55)
    assert result == {"cancelled": True, "run_id": 55}


async def test_cancel_workflow_run_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await actions.cancel_workflow_run("o", "r", 55)
    assert exc.value.status_code == 403


async def test_list_workflow_runs_filters(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"workflow_runs": [
                {"id": 9, "name": "CI", "status": "completed",
                 "conclusion": "success"}
            ]},
        )

    install_mock(monkeypatch, handler)
    result = await actions.list_workflow_runs("o", "r", branch="main",
                                             status="completed")
    assert result[0]["conclusion"] == "success"
    assert captured["params"]["branch"] == "main"
    assert captured["params"]["status"] == "completed"


async def test_list_workflow_run_jobs_flags_failed_steps(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs/99/jobs"
        return httpx.Response(
            200,
            json={"jobs": [{
                "id": 5, "name": "Test", "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {"name": "setup", "conclusion": "success"},
                    {"name": "pytest", "conclusion": "failure"},
                ],
            }]},
        )

    install_mock(monkeypatch, handler)
    result = await actions.list_workflow_run_jobs("o", "r", 99)
    assert result[0]["conclusion"] == "failure"
    assert result[0]["failed_steps"] == ["pytest"]


async def test_get_job_logs_tails(monkeypatch):
    log = "line\n" * 100  # 500 chars

    def handler(request):
        assert request.url.path == "/repos/o/r/actions/jobs/5/logs"
        return httpx.Response(200, text=log)

    install_mock(monkeypatch, handler)
    result = await actions.get_job_logs("o", "r", 5, max_chars=20, tail=True)
    assert result["truncated"] is True
    assert len(result["logs"]) == 20
    assert result["logs"] == log[-20:]


async def test_rerun_workflow_run_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(201), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await actions.rerun_workflow_run("o", "r", 99)
    assert exc.value.status_code == 403


async def test_rerun_workflow_run_failed_only_endpoint(monkeypatch):
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(201, json={})

    install_mock(monkeypatch, handler)
    result = await actions.rerun_workflow_run("o", "r", 99, failed_only=True)
    assert captured["method"] == "POST"
    assert captured["path"] == "/repos/o/r/actions/runs/99/rerun-failed-jobs"
    assert result == {"rerun": True, "run_id": 99, "failed_only": True}


async def test_trigger_workflow_posts_ref_and_inputs(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/actions/workflows/ci.yml/dispatches"
        captured["body"] = json.loads(request.content)
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await actions.trigger_workflow("o", "r", "ci.yml", "main",
                                           inputs={"env": "prod"})
    assert captured["body"] == {"ref": "main", "inputs": {"env": "prod"}}
    assert result["dispatched"] is True


async def test_trigger_workflow_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await actions.trigger_workflow("o", "r", "ci.yml", "main")
    assert exc.value.status_code == 403


async def test_create_scheduled_workflow_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await actions.create_scheduled_workflow("o", "r", "Nightly", "0 9 * * *",
                                               "echo hi")
    assert exc.value.status_code == 403


async def test_create_scheduled_workflow_bad_cron(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await actions.create_scheduled_workflow("o", "r", "x", "not cron", "echo")
    assert exc.value.status_code == 400


async def test_create_scheduled_workflow_commits_yaml(monkeypatch):
    import base64
    captured = {}

    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/repos/o/r":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.method == "GET" and p.startswith("/repos/o/r/contents/"):
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "PUT" and p == "/repos/o/r/contents/.github/workflows/nightly-backup.yml":
            captured["body"] = json.loads(request.content)
            captured["path"] = p
            return httpx.Response(
                201,
                json={"content": {"path": ".github/workflows/nightly-backup.yml",
                                  "sha": "s", "html_url": "u"},
                      "commit": {"sha": "c"}},
            )
        raise AssertionError(f"unexpected {request.method} {p}")

    install_mock(monkeypatch, handler)
    result = await actions.create_scheduled_workflow(
        "o", "r", "Nightly Backup", "0 9 * * 1", "echo hi\nrun-backup.sh"
    )
    body = captured["body"]
    assert body["branch"] == "main"  # defaulted to default branch
    assert "sha" not in body  # new file
    yaml = base64.b64decode(body["content"]).decode()
    assert "schedule:" in yaml
    assert 'cron: "0 9 * * 1"' in yaml
    assert "workflow_dispatch: {}" in yaml
    assert "run-backup.sh" in yaml
    assert result["cron"] == "0 9 * * 1"
    assert result["branch"] == "main"
