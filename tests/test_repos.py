"""Tests for github_mcp.repos."""

import httpx
import pytest

from github_mcp import repos, server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    cfg = Config(token=token, api_url="https://api.github.com",
                 read_only=read_only, timeout=5.0, user_agent="test-agent")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(server, "GitHubClient",
                        lambda c: GitHubClient(c, transport=transport))


async def test_get_rate_limit_filters_buckets(monkeypatch):
    def handler(request):
        assert request.url.path == "/rate_limit"
        return httpx.Response(200, json={"resources": {
            "core": {"limit": 5000, "remaining": 4999, "reset": 1},
            "search": {"limit": 30, "remaining": 30, "reset": 2},
            "graphql": {"limit": 5000, "remaining": 5000, "reset": 3},
            "code_search": {"limit": 10, "remaining": 10, "reset": 4}}})

    install_mock(monkeypatch, handler)
    result = await repos.get_rate_limit()
    assert set(result) == {"core", "search", "graphql"}  # code_search dropped
    assert result["core"]["remaining"] == 4999


async def test_get_user(monkeypatch):
    def handler(request):
        assert request.url.path == "/users/octocat"
        return httpx.Response(200, json={"login": "octocat", "type": "User",
                                         "public_repos": 8, "extra": 1})

    install_mock(monkeypatch, handler)
    result = await repos.get_user("octocat")
    assert result["login"] == "octocat"
    assert "extra" not in result


async def test_list_repository_languages(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/languages"
        return httpx.Response(200, json={"Python": 12345, "Shell": 67})

    install_mock(monkeypatch, handler)
    result = await repos.list_repository_languages("o", "r")
    assert result["Python"] == 12345


async def test_replace_repository_topics(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/topics"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"names": ["mcp", "github"]})

    install_mock(monkeypatch, handler)
    result = await repos.replace_repository_topics("o", "r", ["mcp", "github"])
    assert captured["body"] == {"names": ["mcp", "github"]}
    assert result["names"] == ["mcp", "github"]


async def test_update_repository_sends_only_set_fields(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"full_name": "o/r",
                                         "stargazers_count": 0})

    install_mock(monkeypatch, handler)
    await repos.update_repository("o", "r", description="new")
    assert captured["body"] == {"description": "new"}  # nothing else sent


async def test_create_commit_status(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/statuses/abc"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"state": "success", "context": "ci/x",
                                         "description": "ok", "target_url": None})

    install_mock(monkeypatch, handler)
    result = await repos.create_commit_status("o", "r", "abc", "success",
                                              context="ci/x", description="ok")
    assert captured["body"]["state"] == "success"
    assert result["context"] == "ci/x"


async def test_update_repository_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.update_repository("o", "r", description="x")
    assert exc.value.status_code == 403
