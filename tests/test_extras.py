"""Tests for github_mcp.extras."""

import json

import httpx
import pytest

from github_mcp import extras, server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    cfg = Config(token=token, api_url="https://api.github.com",
                 read_only=read_only, timeout=5.0, user_agent="t")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(server, "GitHubClient",
                        lambda c: GitHubClient(c, transport=transport))


async def test_update_pull_request_branch(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/pulls/4/update-branch"
        return httpx.Response(202, json={"message": "Updating pull request branch."})

    install_mock(monkeypatch, handler)
    result = await extras.update_pull_request_branch("o", "r", 4)
    assert result["updating"] is True
    assert "Updating" in result["message"]


async def test_update_issue_comment(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/issues/comments/88"
        assert json.loads(request.content) == {"body": "edited"}
        return httpx.Response(200, json={"id": 88, "body": "edited",
            "user": {"login": "jd"}, "created_at": "t", "html_url": "u"})

    install_mock(monkeypatch, handler)
    result = await extras.update_issue_comment("o", "r", 88, "edited")
    assert result["id"] == 88
    assert result["body"] == "edited"


async def test_delete_issue_comment(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/issues/comments/88"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await extras.delete_issue_comment("o", "r", 88)
    assert result == {"deleted": True, "comment_id": 88}


async def test_delete_release_asset(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/releases/assets/12"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await extras.delete_release_asset("o", "r", 12)
    assert result == {"deleted": True, "asset_id": 12}


async def test_download_release_asset_returns_url(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/releases/assets/12"
        return httpx.Response(200, json={"id": 12, "name": "wheel.whl",
            "size": 50, "content_type": "application/zip", "download_count": 3,
            "browser_download_url": "https://x/wheel.whl"})

    install_mock(monkeypatch, handler)
    result = await extras.download_release_asset("o", "r", 12)
    assert result["browser_download_url"] == "https://x/wheel.whl"
    assert result["name"] == "wheel.whl"


async def test_delete_gist(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/gists/abc123"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await extras.delete_gist("abc123")
    assert result == {"deleted": True, "gist_id": "abc123"}


async def test_mark_all_notifications_read(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/notifications"
        return httpx.Response(202, json={"message": "ok"})

    install_mock(monkeypatch, handler)
    result = await extras.mark_all_notifications_read()
    assert result["marked_read"] is True


async def test_delete_gist_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await extras.delete_gist("abc123")
    assert exc.value.status_code == 403
