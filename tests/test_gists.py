"""Tests for github_mcp.gists."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import core, gists
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


async def test_create_gist_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(201, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await gists.create_gist({"a.txt": "x"})
    assert exc.value.status_code == 403


async def test_create_gist_posts_files(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/gists"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"id": "g1", "description": "d", "public": False,
                  "files": {"a.txt": {}}, "html_url": "u"},
        )

    install_mock(monkeypatch, handler)
    result = await gists.create_gist({"a.txt": "hello"}, description="d")
    assert captured["body"]["files"] == {"a.txt": {"content": "hello"}}
    assert captured["body"]["public"] is False
    assert result["files"] == ["a.txt"]


async def test_list_gists(monkeypatch):
    def handler(request):
        assert request.url.path == "/gists"
        return httpx.Response(200, json=[
            {"id": "g1", "description": "d", "public": True,
             "files": {"a.txt": {}}, "html_url": "u"}])

    install_mock(monkeypatch, handler)
    result = await gists.list_gists()
    assert result[0]["id"] == "g1"
    assert result[0]["files"] == ["a.txt"]


async def test_get_gist_includes_content(monkeypatch):
    def handler(request):
        assert request.url.path == "/gists/g1"
        return httpx.Response(200, json={"id": "g1", "description": "d",
                                         "public": True, "html_url": "u",
                                         "files": {"a.txt": {"content": "hello"}}})

    install_mock(monkeypatch, handler)
    result = await gists.get_gist("g1")
    assert result["files"]["a.txt"] == "hello"


async def test_update_gist(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/gists/g1"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "g1", "description": "new",
                                         "public": False, "files": {"a": {}},
                                         "html_url": "u"})

    install_mock(monkeypatch, handler)
    result = await gists.update_gist("g1", {"a.txt": "new content"},
                                      description="new")
    assert captured["body"]["files"]["a.txt"]["content"] == "new content"
    assert result["id"] == "g1"


async def test_delete_gist(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/gists/abc123"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await gists.delete_gist("abc123")
    assert result == {"deleted": True, "gist_id": "abc123"}


async def test_delete_gist_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await gists.delete_gist("abc123")
    assert exc.value.status_code == 403
