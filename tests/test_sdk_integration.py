"""Guards on how the connector sits on the mcp 2.x SDK.

mcp 2.x treats any exception escaping a tool as a crash and replaces its text
with a bare ``Error executing tool <name>``. Only ``ToolError`` keeps its
message. ``GitHubError`` subclasses it so the model still learns *why* a call
failed; these tests fail if that ever regresses, e.g. after an SDK upgrade.
"""

from __future__ import annotations

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

import github_mcp
from github_mcp import core
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, read_only=False):
    cfg = Config(
        token="test-token",
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
        max_retries=0,
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(core, "config", cfg)
    monkeypatch.setattr(core, "GitHubClient", lambda c: GitHubClient(c, transport=transport))


def test_github_error_is_an_anticipated_tool_error():
    assert issubclass(GitHubError, ToolError)
    assert issubclass(GitHubError, RuntimeError)  # back-compat for `except RuntimeError`
    assert not issubclass(GitHubError, UnexpectedToolError)


async def test_api_error_text_reaches_the_model(monkeypatch):
    install_mock(monkeypatch, lambda req: httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(ToolError) as excinfo:
        await core.mcp.call_tool("get_repository", {"owner": "o", "repo": "missing"})
    assert not isinstance(excinfo.value, UnexpectedToolError)
    message = str(excinfo.value)
    assert "(404)" in message and "Not Found" in message


async def test_read_only_refusal_text_reaches_the_model(monkeypatch):
    def handler(req):  # pragma: no cover - must never be called
        raise AssertionError("write reached the API in read-only mode")

    install_mock(monkeypatch, handler, read_only=True)
    with pytest.raises(ToolError) as excinfo:
        await core.mcp.call_tool("create_issue", {"owner": "o", "repo": "r", "title": "t"})
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "read-only mode" in str(excinfo.value)


async def test_network_failure_text_reaches_the_model(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("connection refused")

    install_mock(monkeypatch, handler)
    with pytest.raises(ToolError) as excinfo:
        await core.mcp.call_tool("get_repository", {"owner": "o", "repo": "r"})
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "connection refused" in str(excinfo.value)


def test_server_reports_the_connector_version():
    # serverInfo.version in the initialize handshake; lets you confirm which
    # release a connector is running.
    assert core.SERVER_VERSION == github_mcp.__version__
