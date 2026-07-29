"""Tests for github_mcp.issues."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import core, issues, notifications, pulls
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


async def test_create_issue_blocked_in_read_only(monkeypatch):
    install_mock(
        monkeypatch, lambda r: httpx.Response(200, json={}), read_only=True
    )
    with pytest.raises(GitHubError) as exc_info:
        await issues.create_issue("o", "r", "title")
    assert exc_info.value.status_code == 403


async def test_create_issue_posts_payload(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "POST"
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"number": 7, "title": "title", "state": "open", "body": "desc"},
        )

    install_mock(monkeypatch, handler)
    result = await issues.create_issue(
        "o", "r", "title", body="desc", labels=["bug"]
    )
    assert captured["body"] == {"title": "title", "body": "desc", "labels": ["bug"]}
    assert result["number"] == 7


async def test_update_issue_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await issues.update_issue("o", "r", 1, state="closed")
    assert exc.value.status_code == 403


async def test_update_issue_requires_a_field(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await issues.update_issue("o", "r", 1)
    assert exc.value.status_code == 400


async def test_update_issue_patches(monkeypatch):
    captured = {}

    def handler(request):
        import json
        assert request.method == "PATCH"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"number": 1, "state": "closed", "title": "t"}
        )

    install_mock(monkeypatch, handler)
    result = await issues.update_issue("o", "r", 1, state="closed")
    assert captured["body"] == {"state": "closed"}
    assert result["state"] == "closed"


async def test_list_issue_comments(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/issues/4/comments"
        return httpx.Response(
            200, json=[{"id": 1, "user": {"login": "jd"}, "body": "hi"}]
        )

    install_mock(monkeypatch, handler)
    result = await issues.list_issue_comments("o", "r", 4)
    assert result[0]["user"] == "jd"
    assert result[0]["body"] == "hi"


async def test_add_labels(monkeypatch):
    captured = {}

    def handler(request):
        import json
        assert request.url.path == "/repos/o/r/issues/4/labels"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[{"name": "bug"}, {"name": "p1"}])

    install_mock(monkeypatch, handler)
    result = await issues.add_labels("o", "r", 4, ["bug", "p1"])
    assert captured["body"] == {"labels": ["bug", "p1"]}
    assert result["labels"] == ["bug", "p1"]


async def test_remove_label_returns_remaining(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/issues/4/labels/bug"
        return httpx.Response(200, json=[{"name": "p1"}])

    install_mock(monkeypatch, handler)
    result = await issues.remove_label("o", "r", 4, "bug")
    assert result == {"removed": "bug", "labels": ["p1"]}


async def test_add_assignees(monkeypatch):
    def handler(request):
        import json
        assert request.url.path == "/repos/o/r/issues/4/assignees"
        assert json.loads(request.content) == {"assignees": ["jd"]}
        return httpx.Response(
            201, json={"number": 4, "assignees": [{"login": "jd"}]}
        )

    install_mock(monkeypatch, handler)
    result = await issues.add_assignees("o", "r", 4, ["jd"])
    assert result["assignees"] == ["jd"]


@pytest.mark.parametrize("call", [
    lambda: pulls.add_pull_request_review_comment("o", "r", 1, "b", "s", "a.py", 1),
    lambda: pulls.update_pull_request("o", "r", 1, state="closed"),
    lambda: notifications.mark_notification_read("9"),
    lambda: issues.add_labels("o", "r", 1, ["bug"]),
    lambda: issues.remove_label("o", "r", 1, "bug"),
    lambda: issues.add_assignees("o", "r", 1, ["jd"]),
])
async def test_new_write_tools_blocked_in_read_only(monkeypatch, call):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await call()
    assert exc.value.status_code == 403


async def test_remove_label_percent_encodes_name(monkeypatch):
    captured = {}

    def handler(request):
        captured["path"] = request.url.raw_path.decode()
        return httpx.Response(200, json=[])

    install_mock(monkeypatch, handler)
    await issues.remove_label("o", "r", 4, "type/bug")
    # the slash in the label must be encoded, not treated as a path separator
    assert "type%2Fbug" in captured["path"]
    assert "/labels/type/bug" not in captured["path"]


async def test_list_labels(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/labels"
        return httpx.Response(200, json=[
            {"name": "bug", "color": "d73a4a", "description": "broken"}])

    install_mock(monkeypatch, handler)
    result = await issues.list_labels("o", "r")
    assert result[0]["name"] == "bug"
    assert result[0]["color"] == "d73a4a"


async def test_create_label_strips_hash(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/labels"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"name": "bug", "color": "d73a4a",
                                         "description": "x"})

    install_mock(monkeypatch, handler)
    result = await issues.create_label("o", "r", "bug", color="#d73a4a")
    assert captured["body"]["color"] == "d73a4a"  # leading # stripped
    assert result["name"] == "bug"


async def test_update_label(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/labels/bug"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"name": "defect", "color": "ff0000",
                                         "description": "x"})

    install_mock(monkeypatch, handler)
    result = await issues.update_label("o", "r", "bug", new_name="defect",
                                       color="#ff0000")
    assert captured["body"]["new_name"] == "defect"
    assert captured["body"]["color"] == "ff0000"
    assert result["name"] == "defect"


async def test_delete_label(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/labels/bug"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await issues.delete_label("o", "r", "bug")
    assert result == {"deleted": True, "name": "bug"}


async def test_delete_label_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await issues.delete_label("o", "r", "bug")
    assert exc.value.status_code == 403


async def test_update_issue_comment(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/issues/comments/88"
        assert json.loads(request.content) == {"body": "edited"}
        return httpx.Response(200, json={"id": 88, "body": "edited",
            "user": {"login": "jd"}, "created_at": "t", "html_url": "u"})

    install_mock(monkeypatch, handler)
    result = await issues.update_issue_comment("o", "r", 88, "edited")
    assert result["id"] == 88
    assert result["body"] == "edited"


async def test_delete_issue_comment(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/issues/comments/88"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await issues.delete_issue_comment("o", "r", 88)
    assert result == {"deleted": True, "comment_id": 88}
