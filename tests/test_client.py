"""Tests for the GitHub REST client wrapper using a mocked transport."""

import httpx
import pytest

from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def make_config(**overrides):
    base = dict(
        token="test-token",
        api_url="https://api.github.com",
        read_only=False,
        timeout=5.0,
        user_agent="test-agent",
    )
    base.update(overrides)
    return Config(**base)


async def test_get_sends_auth_and_returns_json():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["accept"] = request.headers.get("Accept")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"login": "octocat"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(make_config(), transport=transport) as gh:
        result = await gh.get("/user")

    assert result == {"login": "octocat"}
    assert captured["auth"] == "Bearer test-token"
    assert "vnd.github+json" in captured["accept"]


async def test_params_with_none_are_dropped():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with GitHubClient(make_config(), transport=transport) as gh:
        await gh.get("/repos/o/r/commits", params={"sha": "main", "path": None})

    assert captured["query"] == {"sha": "main"}


async def test_error_response_raises_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(make_config(), transport=transport) as gh:
        with pytest.raises(GitHubError) as exc_info:
            await gh.get("/repos/o/missing")

    assert exc_info.value.status_code == 404
    assert "Not Found" in str(exc_info.value)


async def test_get_raw_passes_custom_accept():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["accept"] = request.headers.get("Accept")
        return httpx.Response(200, text="diff --git a b")

    transport = httpx.MockTransport(handler)
    async with GitHubClient(make_config(), transport=transport) as gh:
        text = await gh.get_raw(
            "/repos/o/r/pulls/1", accept="application/vnd.github.diff"
        )

    assert text == "diff --git a b"
    assert captured["accept"] == "application/vnd.github.diff"
