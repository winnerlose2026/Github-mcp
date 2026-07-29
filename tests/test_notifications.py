"""Tests for github_mcp.notifications."""

from __future__ import annotations

import httpx

from github_mcp import core, notifications
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


async def test_list_notifications(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/notifications"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=[{"id": "99", "reason": "review_requested", "unread": True,
                   "subject": {"title": "PR x", "type": "PullRequest"},
                   "repository": {"full_name": "o/r"}}],
        )

    install_mock(monkeypatch, handler)
    result = await notifications.list_notifications(all=True)
    assert result[0]["title"] == "PR x"
    assert captured["params"]["all"] == "true"


async def test_mark_notification_read(monkeypatch):
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(205)

    install_mock(monkeypatch, handler)
    result = await notifications.mark_notification_read("99")
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/notifications/threads/99"
    assert result == {"marked_read": True, "thread_id": "99"}


async def test_mark_all_notifications_read(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/notifications"
        return httpx.Response(202, json={"message": "ok"})

    install_mock(monkeypatch, handler)
    result = await notifications.mark_all_notifications_read()
    assert result["marked_read"] is True
