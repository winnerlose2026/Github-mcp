"""Tests for github_mcp.issues."""

import httpx

from github_mcp import issues, server
from github_mcp.client import GitHubClient
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    cfg = Config(token=token, api_url="https://api.github.com",
                 read_only=read_only, timeout=5.0, user_agent="test-agent")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(server, "GitHubClient",
                        lambda c: GitHubClient(c, transport=transport))


async def test_list_milestones(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/milestones"
        assert request.url.params["state"] == "open"
        return httpx.Response(200, json=[{"number": 1, "title": "v1",
                                          "state": "open", "open_issues": 3,
                                          "closed_issues": 2, "due_on": None,
                                          "html_url": "u"}])

    install_mock(monkeypatch, handler)
    result = await issues.list_milestones("o", "r")
    assert result[0]["number"] == 1
    assert result[0]["open_issues"] == 3


async def test_create_milestone(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/milestones"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"number": 4, "title": "v2",
                                         "state": "open", "html_url": "u"})

    install_mock(monkeypatch, handler)
    result = await issues.create_milestone("o", "r", "v2", due_on="2026-12-31T00:00:00Z")
    assert captured["body"]["title"] == "v2"
    assert captured["body"]["due_on"] == "2026-12-31T00:00:00Z"
    assert result["number"] == 4


async def test_lock_and_unlock_issue(monkeypatch):
    import json
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "PUT":
            assert json.loads(request.content)["lock_reason"] == "spam"
            return httpx.Response(204)
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError("unexpected")

    install_mock(monkeypatch, handler)
    locked = await issues.lock_issue("o", "r", 7, lock_reason="spam")
    assert locked["locked"] is True
    unlocked = await issues.unlock_issue("o", "r", 7)
    assert unlocked["locked"] is False
    assert ("PUT", "/repos/o/r/issues/7/lock") in seen
    assert ("DELETE", "/repos/o/r/issues/7/lock") in seen


async def test_list_pull_request_commits(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/9/commits"
        return httpx.Response(200, json=[
            {"sha": "abc", "commit": {"message": "m",
                                      "author": {"name": "JD", "date": "2024"}}}])

    install_mock(monkeypatch, handler)
    result = await issues.list_pull_request_commits("o", "r", 9)
    assert result[0]["sha"] == "abc"
