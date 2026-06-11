"""Tests for the release/tag deletion tools in github_mcp.releases."""

import httpx
import pytest

from github_mcp import releases, server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the server's session at a mocked GitHub API.

    The deletion tools call `server._session`, which reads `server.config` and
    `server.GitHubClient`, so those are what we patch.
    """
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


async def test_delete_release_by_tag_resolves_then_deletes(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/repos/o/r/releases/tags/v1":
            return httpx.Response(200, json={"id": 42, "tag_name": "v1"})
        if request.method == "DELETE" and request.url.path == "/repos/o/r/releases/42":
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    install_mock(monkeypatch, handler)
    result = await releases.delete_release("o", "r", tag="v1")
    assert result == {"deleted_release": True, "release_id": 42, "tag": "v1"}
    assert ("GET", "/repos/o/r/releases/tags/v1") in seen


async def test_delete_release_by_id_skips_lookup(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/releases/99"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await releases.delete_release("o", "r", release_id=99)
    assert result["deleted_release"] is True
    assert result["release_id"] == 99


async def test_delete_release_requires_tag_or_id(monkeypatch):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("API should not be called without tag/release_id")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await releases.delete_release("o", "r")
    assert exc.value.status_code == 422


async def test_delete_release_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await releases.delete_release("o", "r", release_id=1)
    assert exc.value.status_code == 403


async def test_delete_tag_deletes_ref(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/git/refs/tags/v1"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await releases.delete_tag("o", "r", "v1")
    assert result == {"deleted_tag": True, "tag": "v1", "ref": "tags/v1"}


async def test_delete_tag_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await releases.delete_tag("o", "r", "v1")
    assert exc.value.status_code == 403


async def test_delete_release_and_tag_removes_both(monkeypatch):
    def handler(request):
        m, p = request.method, request.url.path
        if m == "GET" and p == "/repos/o/r/releases/tags/v1":
            return httpx.Response(200, json={"id": 42})
        if m == "DELETE" and p == "/repos/o/r/releases/42":
            return httpx.Response(204)
        if m == "DELETE" and p == "/repos/o/r/git/refs/tags/v1":
            return httpx.Response(204)
        raise AssertionError(f"unexpected {m} {p}")

    install_mock(monkeypatch, handler)
    result = await releases.delete_release_and_tag("o", "r", "v1")
    assert result == {
        "tag": "v1",
        "release_deleted": True,
        "release_id": 42,
        "tag_deleted": True,
    }


async def test_delete_release_and_tag_tolerates_missing_release(monkeypatch):
    def handler(request):
        m, p = request.method, request.url.path
        if m == "GET" and p == "/repos/o/r/releases/tags/v1":
            return httpx.Response(404, json={"message": "Not Found"})
        if m == "DELETE" and p == "/repos/o/r/git/refs/tags/v1":
            return httpx.Response(204)
        raise AssertionError(f"unexpected {m} {p}")

    install_mock(monkeypatch, handler)
    result = await releases.delete_release_and_tag("o", "r", "v1")
    assert result["release_deleted"] is False
    assert result["release_id"] is None
    assert result["tag_deleted"] is True
