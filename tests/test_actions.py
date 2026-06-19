"""Tests for github_mcp.actions."""

import httpx
import pytest

from github_mcp import actions, server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    cfg = Config(token=token, api_url="https://api.github.com",
                 read_only=read_only, timeout=5.0, user_agent="test-agent")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(server, "GitHubClient",
                        lambda c: GitHubClient(c, transport=transport))


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
