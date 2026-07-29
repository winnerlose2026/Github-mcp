"""Tests for github_mcp.deployments."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import core, deployments
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


async def test_list_pending_deployments(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs/5/pending_deployments"
        return httpx.Response(200, json=[
            {"environment": {"id": 9, "name": "pypi"}, "wait_timer": 0,
             "current_user_can_approve": True,
             "reviewers": [{"type": "User", "reviewer": {"login": "jd"}}]},
        ])

    install_mock(monkeypatch, handler)
    result = await deployments.list_pending_deployments("o", "r", 5)
    assert result[0]["environment"] == "pypi"
    assert result[0]["environment_id"] == 9
    assert result[0]["current_user_can_approve"] is True
    assert result[0]["reviewers"] == ["jd"]


async def test_review_deployment_approves(monkeypatch):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/actions/runs/5/pending_deployments"
        payload = json.loads(request.content)
        assert payload == {"environment_ids": [9], "state": "approved",
                           "comment": "ship it"}
        return httpx.Response(200, json=[{"id": 1}])

    install_mock(monkeypatch, handler)
    result = await deployments.review_deployment("o", "r", 5, [9], "approved",
                                                 comment="ship it")
    assert result["reviewed"] is True
    assert result["state"] == "approved"


async def test_review_deployment_rejects_bad_state(monkeypatch):
    def handler(request):  # pragma: no cover
        raise AssertionError("should not call API")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await deployments.review_deployment("o", "r", 5, [9], "maybe")
    assert exc.value.status_code == 422


async def test_review_deployment_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json=[]), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await deployments.review_deployment("o", "r", 5, [9], "approved")
    assert exc.value.status_code == 403
