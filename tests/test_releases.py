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


async def test_update_release_by_tag_resolves_then_patches(monkeypatch):
    import json
    captured = {}

    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/repos/o/r/releases/tags/v1":
            return httpx.Response(200, json={"id": 42, "tag_name": "v1"})
        if request.method == "PATCH" and p == "/repos/o/r/releases/42":
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"tag_name": "v1", "name": "First",
                                             "draft": False, "prerelease": False})
        raise AssertionError(f"unexpected {request.method} {p}")

    install_mock(monkeypatch, handler)
    result = await releases.update_release("o", "r", tag="v1", name="First")
    assert captured["body"] == {"name": "First"}  # only changed field
    assert result["name"] == "First"


async def test_update_release_requires_identifier(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await releases.update_release("o", "r")
    assert exc.value.status_code == 422


async def test_generate_release_notes(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/releases/generate-notes"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"name": "v2", "body": "## Changes\n- x"})

    install_mock(monkeypatch, handler)
    result = await releases.generate_release_notes("o", "r", "v2",
                                                   previous_tag_name="v1")
    assert captured["body"]["tag_name"] == "v2"
    assert captured["body"]["previous_tag_name"] == "v1"
    assert result["body"].startswith("## Changes")


async def test_list_release_assets(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/releases/tags/v1"
        return httpx.Response(200, json={"id": 1, "assets": [
            {"id": 9, "name": "app.zip", "label": None, "size": 100,
             "content_type": "application/zip", "download_count": 3,
             "browser_download_url": "u"}]})

    install_mock(monkeypatch, handler)
    result = await releases.list_release_assets("o", "r", "v1")
    assert result[0]["name"] == "app.zip"
    assert result[0]["download_count"] == 3


async def test_upload_release_asset(monkeypatch):
    import base64
    seen = {}

    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/repos/o/r/releases/tags/v1":
            return httpx.Response(200, json={"id": 1,
                "upload_url": "https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}"})
        if request.method == "POST" and "uploads.github.com" in str(request.url):
            seen["host"] = request.url.host
            seen["name"] = request.url.params.get("name")
            seen["ctype"] = request.headers.get("Content-Type")
            seen["body"] = request.content
            return httpx.Response(201, json={"id": 9, "name": "a.bin",
                                             "size": 3, "state": "uploaded",
                                             "browser_download_url": "u"})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    install_mock(monkeypatch, handler)
    payload = base64.b64encode(b"abc").decode()
    result = await releases.upload_release_asset("o", "r", "v1", "a.bin",
                                                 payload, content_type="application/octet-stream")
    assert seen["host"] == "uploads.github.com"
    assert seen["name"] == "a.bin"
    assert seen["body"] == b"abc"  # base64 decoded to raw bytes
    assert result["state"] == "uploaded"


async def test_upload_release_asset_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await releases.upload_release_asset("o", "r", "v1", "a.bin", "YWJj")
    assert exc.value.status_code == 403
