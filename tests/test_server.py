"""Tests for the MCP tool functions, with the GitHub API mocked."""

import httpx
import pytest

from github_mcp import server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the server's tools at a mocked GitHub API."""
    cfg = Config(
        token=token,
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(
        server,
        "GitHubClient",
        lambda c: GitHubClient(c, transport=transport),
    )


async def test_get_authenticated_user(monkeypatch):
    def handler(request):
        assert request.url.path == "/user"
        return httpx.Response(
            200, json={"login": "octocat", "name": "The Octocat", "public_repos": 8}
        )

    install_mock(monkeypatch, handler)
    result = await server.get_authenticated_user()
    assert result["login"] == "octocat"
    assert result["public_repos"] == 8


async def test_missing_token_raises(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}), token=None)
    with pytest.raises(GitHubError) as exc_info:
        await server.get_authenticated_user()
    assert exc_info.value.status_code == 401


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
    result = await server.search_repositories("mcp")
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
    await server.search_repositories("x", limit=999)
    assert captured["per_page"] == "50"


async def test_get_file_contents_decodes_base64(monkeypatch):
    import base64

    encoded = base64.b64encode(b"hello world").decode()

    def handler(request):
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "encoding": "base64",
                "content": encoded,
                "size": 11,
            },
        )

    install_mock(monkeypatch, handler)
    result = await server.get_file_contents("o", "r", "README.md")
    assert result["type"] == "file"
    assert result["content"] == "hello world"


async def test_get_file_contents_directory_listing(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {"name": "a.py", "path": "src/a.py", "type": "file"},
                {"name": "sub", "path": "src/sub", "type": "dir"},
            ],
        )

    install_mock(monkeypatch, handler)
    result = await server.get_file_contents("o", "r", "src")
    assert result["type"] == "directory"
    assert len(result["entries"]) == 2


async def test_get_pull_request_diff_truncates(monkeypatch):
    big_diff = "x" * 100

    def handler(request):
        assert request.headers["Accept"] == "application/vnd.github.diff"
        return httpx.Response(200, text=big_diff)

    install_mock(monkeypatch, handler)
    result = await server.get_pull_request_diff("o", "r", 1, max_chars=10)
    assert result["truncated"] is True
    assert len(result["diff"]) == 10


async def test_create_issue_blocked_in_read_only(monkeypatch):
    install_mock(
        monkeypatch, lambda r: httpx.Response(200, json={}), read_only=True
    )
    with pytest.raises(GitHubError) as exc_info:
        await server.create_issue("o", "r", "title")
    assert exc_info.value.status_code == 403


async def test_create_issue_posts_payload(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "POST"
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"number": 7, "title": "title", "state": "open", "body": "desc"},
        )

    install_mock(monkeypatch, handler)
    result = await server.create_issue(
        "o", "r", "title", body="desc", labels=["bug"]
    )
    assert captured["body"] == {"title": "title", "body": "desc", "labels": ["bug"]}
    assert result["number"] == 7
