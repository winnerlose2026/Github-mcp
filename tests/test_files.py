"""Tests for github_mcp.files."""

from __future__ import annotations

import json

import httpx

from github_mcp import core, files
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
    result = await files.get_file_contents("o", "r", "README.md")
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
    result = await files.get_file_contents("o", "r", "src")
    assert result["type"] == "directory"
    assert len(result["entries"]) == 2


async def test_create_or_update_file_updates_existing(monkeypatch):
    import base64
    captured = {}

    def handler(request):
        path = "/repos/o/r/contents/notes.md"
        if request.method == "GET" and request.url.path == path:
            # existing file -> returns its blob sha
            return httpx.Response(200, json={"sha": "oldsha", "path": "notes.md"})
        if request.method == "PUT" and request.url.path == path:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"content": {"path": "notes.md", "sha": "newsha"},
                      "commit": {"sha": "commitsha"}},
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    install_mock(monkeypatch, handler)
    result = await files.create_or_update_file(
        "o", "r", "notes.md", "hello", "msg", branch="main"
    )
    # content base64-encoded, and the existing sha auto-looked-up
    assert base64.b64decode(captured["body"]["content"]).decode() == "hello"
    assert captured["body"]["sha"] == "oldsha"
    assert captured["body"]["branch"] == "main"
    assert result["commit_sha"] == "commitsha"
    assert result["created"] is False


async def test_create_or_update_file_creates_new_on_404(monkeypatch):
    captured = {}

    def handler(request):
        path = "/repos/o/r/contents/new.md"
        if request.method == "GET" and request.url.path == path:
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "PUT" and request.url.path == path:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={"content": {"path": "new.md", "sha": "s"},
                      "commit": {"sha": "c"}},
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    install_mock(monkeypatch, handler)
    result = await files.create_or_update_file("o", "r", "new.md", "x", "add")
    assert "sha" not in captured["body"]  # no sha -> create
    assert result["created"] is True


async def test_delete_file_looks_up_sha(monkeypatch):
    captured = {}

    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/repos/o/r/contents/old.txt":
            return httpx.Response(200, json={"sha": "blobsha"})
        if request.method == "DELETE" and p == "/repos/o/r/contents/old.txt":
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"commit": {"sha": "c1"}})
        raise AssertionError(f"unexpected {request.method} {p}")

    install_mock(monkeypatch, handler)
    result = await files.delete_file("o", "r", "old.txt", "remove it")
    assert captured["body"]["sha"] == "blobsha"  # auto-looked up
    assert result["commit_sha"] == "c1"
