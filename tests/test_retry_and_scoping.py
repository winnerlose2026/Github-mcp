"""Tests for the retry policy, tool-group scoping, and pagination plumbing."""

from __future__ import annotations

import httpx
import pytest

from github_mcp import core, issues
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import TOOL_GROUPS, Config, _read_tool_groups


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False,
                 max_retries=3):
    cfg = Config(
        token=token,
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
        max_retries=max_retries,
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(core, "config", cfg)
    monkeypatch.setattr(
        core, "GitHubClient", lambda c: GitHubClient(c, transport=transport)
    )


# --- retry policy ----------------------------------------------------------


async def test_read_retries_after_rate_limit(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(
                429, headers={"retry-after": "0"}, json={"message": "rate limit"}
            )
        return httpx.Response(200, json=[])

    install_mock(monkeypatch, handler)
    await issues.list_issues("o", "r")
    assert calls["n"] == 3, "a throttled read should be retried until it succeeds"


async def test_read_retries_transient_5xx(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 2 else httpx.Response(200, json=[])

    install_mock(monkeypatch, handler)
    await issues.list_issues("o", "r")
    assert calls["n"] == 2


async def test_write_is_not_replayed_on_5xx(monkeypatch):
    """A POST may already have been applied, so it must not be retried."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(502, json={"message": "bad gateway"})

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError):
        await issues.create_issue("o", "r", "title")
    assert calls["n"] == 1, "writes must not be replayed after an ambiguous 5xx"


async def test_write_is_retried_when_only_throttled(monkeypatch):
    """A 429 means the write never happened, so replaying it is safe."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(201, json={"number": 1, "title": "t"})

    install_mock(monkeypatch, handler)
    await issues.create_issue("o", "r", "title")
    assert calls["n"] == 2


async def test_retries_can_be_disabled(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"})

    install_mock(monkeypatch, handler, max_retries=0)
    with pytest.raises(GitHubError):
        await issues.list_issues("o", "r")
    assert calls["n"] == 1


# --- pagination ------------------------------------------------------------


async def test_page_is_sent_in_the_query_string(monkeypatch):
    seen = {}

    def handler(request):
        seen["page"] = request.url.params.get("page")
        seen["per_page"] = request.url.params.get("per_page")
        return httpx.Response(200, json=[])

    install_mock(monkeypatch, handler)
    await issues.list_issues("o", "r", limit=50, page=3)
    assert seen == {"page": "3", "per_page": "50"}


async def test_page_defaults_to_one(monkeypatch):
    seen = {}

    def handler(request):
        seen["page"] = request.url.params.get("page")
        return httpx.Response(200, json=[])

    install_mock(monkeypatch, handler)
    await issues.list_issues("o", "r")
    assert seen["page"] == "1"


# --- tool-group scoping ----------------------------------------------------


def test_tool_groups_defaults_to_all(monkeypatch):
    monkeypatch.delenv("GITHUB_MCP_TOOLS", raising=False)
    assert _read_tool_groups() is None


@pytest.mark.parametrize("raw", ["issues,pulls", "issues pulls", " issues , pulls "])
def test_tool_groups_accepts_commas_and_spaces(monkeypatch, raw):
    monkeypatch.setenv("GITHUB_MCP_TOOLS", raw)
    assert _read_tool_groups() == frozenset({"issues", "pulls"})


def test_unknown_tool_group_is_a_hard_error(monkeypatch):
    monkeypatch.setenv("GITHUB_MCP_TOOLS", "issues,nope")
    with pytest.raises(ValueError) as exc:
        _read_tool_groups()
    assert "nope" in str(exc.value)
    assert "issues" in str(exc.value)  # lists the valid groups


def test_every_group_names_a_real_module():
    import importlib

    for group in TOOL_GROUPS:
        importlib.import_module(f"github_mcp.{group}")


def test_max_retries_parsing(monkeypatch):
    monkeypatch.setenv("GITHUB_MCP_MAX_RETRIES", "5")
    assert Config.from_env().max_retries == 5
    monkeypatch.setenv("GITHUB_MCP_MAX_RETRIES", "not-a-number")
    assert Config.from_env().max_retries == 3
    monkeypatch.setenv("GITHUB_MCP_MAX_RETRIES", "-2")
    assert Config.from_env().max_retries == 0
