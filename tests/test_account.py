"""Tests for github_mcp.account."""

from __future__ import annotations

import httpx
import pytest

from github_mcp import account, core
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


async def test_get_authenticated_user(monkeypatch):
    def handler(request):
        assert request.url.path == "/user"
        return httpx.Response(
            200, json={"login": "octocat", "name": "The Octocat", "public_repos": 8}
        )

    install_mock(monkeypatch, handler)
    result = await account.get_authenticated_user()
    assert result["login"] == "octocat"
    assert result["public_repos"] == 8


async def test_missing_token_raises(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}), token=None)
    with pytest.raises(GitHubError) as exc_info:
        await account.get_authenticated_user()
    assert exc_info.value.status_code == 401
