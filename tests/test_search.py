"""Tests for github_mcp.search."""

from __future__ import annotations

import httpx

from github_mcp import core, search
from github_mcp.client import GitHubClient
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


async def test_search_repositories_summarizes(monkeypatch):
    def handler(request):
        assert request.url.path == "/search/repositories"
        assert request.url.params["q"] == "mcp"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "anthropics/mcp",
                        "description": "demo",
                        "stargazers_count": 42,
                        "extra_field": "ignored",
                    }
                ]
            },
        )

    install_mock(monkeypatch, handler)
    result = await search.search_repositories("mcp")
    assert len(result) == 1
    assert result[0]["full_name"] == "anthropics/mcp"
    assert result[0]["stars"] == 42
    assert "extra_field" not in result[0]


async def test_search_repositories_clamps_limit(monkeypatch):
    captured = {}

    def handler(request):
        captured["per_page"] = request.url.params["per_page"]
        return httpx.Response(200, json={"items": []})

    install_mock(monkeypatch, handler)
    await search.search_repositories("x", limit=999)
    assert captured["per_page"] == "50"


async def test_search_pull_requests_adds_is_pr(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/search/issues"
        captured["q"] = request.url.params["q"]
        return httpx.Response(200, json={"items": [{"number": 5, "title": "t",
                                                    "state": "open"}]})

    install_mock(monkeypatch, handler)
    result = await search.search_pull_requests("repo:o/r is:open")
    assert "is:pr" in captured["q"]
    assert result[0]["number"] == 5


async def test_search_pull_requests_no_double_is_pr(monkeypatch):
    captured = {}

    def handler(request):
        captured["q"] = request.url.params["q"]
        return httpx.Response(200, json={"items": []})

    install_mock(monkeypatch, handler)
    await search.search_pull_requests("is:pr author:me")
    assert captured["q"].count("is:pr") == 1


async def test_search_commits(monkeypatch):
    def handler(request):
        assert request.url.path == "/search/commits"
        return httpx.Response(200, json={"items": [
            {"sha": "abc", "commit": {"message": "fix",
                                      "author": {"name": "JD", "date": "2024"}}}]})

    install_mock(monkeypatch, handler)
    result = await search.search_commits("repo:o/r fix")
    assert result[0]["sha"] == "abc"
    assert result[0]["message"] == "fix"


async def test_search_users(monkeypatch):
    def handler(request):
        assert request.url.path == "/search/users"
        return httpx.Response(200, json={"items": [
            {"login": "octocat", "type": "User", "html_url": "u", "extra": 1}]})

    install_mock(monkeypatch, handler)
    result = await search.search_users("octocat")
    assert result[0]["login"] == "octocat"
    assert "extra" not in result[0]
