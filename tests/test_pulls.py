"""Tests for github_mcp.pulls."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import core, pulls
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


async def test_get_pull_request_diff_truncates(monkeypatch):
    big_diff = "x" * 100

    def handler(request):
        assert request.headers["Accept"] == "application/vnd.github.diff"
        return httpx.Response(200, text=big_diff)

    install_mock(monkeypatch, handler)
    result = await pulls.get_pull_request_diff("o", "r", 1, max_chars=10)
    assert result["truncated"] is True
    assert len(result["diff"]) == 10


async def test_create_pull_request_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await pulls.create_pull_request("o", "r", "t", "feature", "main")
    assert exc.value.status_code == 403


async def test_create_pull_request_posts_payload(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/pulls"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "number": 12,
                "title": "t",
                "state": "open",
                "draft": True,
                "body": "desc",
                "head": {"ref": "feature"},
                "base": {"ref": "main"},
            },
        )

    install_mock(monkeypatch, handler)
    result = await pulls.create_pull_request(
        "o", "r", "t", "feature", "main", body="desc", draft=True
    )
    assert captured["body"]["title"] == "t"
    assert captured["body"]["head"] == "feature"
    assert captured["body"]["base"] == "main"
    assert captured["body"]["draft"] is True
    assert captured["body"]["body"] == "desc"
    assert result["number"] == 12
    assert result["draft"] is True
    assert result["body"] == "desc"


async def test_merge_pull_request_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await pulls.merge_pull_request("o", "r", 1)
    assert exc.value.status_code == 403


async def test_merge_pull_request_puts_payload(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/pulls/5/merge"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"merged": True, "sha": "abc", "message": "Pull Request successfully merged"}
        )

    install_mock(monkeypatch, handler)
    result = await pulls.merge_pull_request(
        "o", "r", 5, merge_method="squash", commit_title="T"
    )
    assert captured["body"]["merge_method"] == "squash"
    assert captured["body"]["commit_title"] == "T"
    assert result["merged"] is True
    assert result["sha"] == "abc"


async def test_merge_pull_request_surfaces_conflict(monkeypatch):
    def handler(request):
        return httpx.Response(405, json={"message": "Pull Request is not mergeable"})

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await pulls.merge_pull_request("o", "r", 5)
    assert exc.value.status_code == 405


async def test_list_pull_request_reviews(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/3/reviews"
        return httpx.Response(
            200,
            json=[{"id": 1, "user": {"login": "jd"}, "state": "APPROVED",
                   "body": "lgtm"}],
        )

    install_mock(monkeypatch, handler)
    result = await pulls.list_pull_request_reviews("o", "r", 3)
    assert result[0]["state"] == "APPROVED"
    assert result[0]["user"] == "jd"


async def test_list_pull_request_review_comments_includes_path(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/4/comments"
        return httpx.Response(
            200,
            json=[{"id": 2, "user": {"login": "jd"}, "body": "nit",
                   "path": "app.py", "line": 10}],
        )

    install_mock(monkeypatch, handler)
    result = await pulls.list_pull_request_review_comments("o", "r", 4)
    assert result[0]["path"] == "app.py"
    assert result[0]["line"] == 10


async def test_submit_pull_request_review_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await pulls.submit_pull_request_review("o", "r", 1, "APPROVE")
    assert exc.value.status_code == 403


async def test_submit_pull_request_review_posts(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/1/reviews"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"id": 1, "user": {"login": "jd"}, "state": "APPROVED"}
        )

    install_mock(monkeypatch, handler)
    result = await pulls.submit_pull_request_review(
        "o", "r", 1, "APPROVE", body="lgtm"
    )
    assert captured["body"] == {"event": "APPROVE", "body": "lgtm"}
    assert result["state"] == "APPROVED"


async def test_add_pull_request_review_comment_posts(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/1/comments"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201, json={"id": 9, "user": {"login": "jd"}, "body": "nit",
                       "path": "app.py", "line": 3}
        )

    install_mock(monkeypatch, handler)
    result = await pulls.add_pull_request_review_comment(
        "o", "r", 1, "nit", "sha1", "app.py", 3
    )
    assert captured["body"]["commit_id"] == "sha1"
    assert captured["body"]["side"] == "RIGHT"
    assert result["path"] == "app.py"


async def test_update_pull_request_requires_field(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await pulls.update_pull_request("o", "r", 1)
    assert exc.value.status_code == 400


async def test_update_pull_request_patches(monkeypatch):
    captured = {}

    def handler(request):
        assert request.method == "PATCH"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"number": 1, "state": "closed", "title": "t",
                       "base": {"ref": "main"}, "head": {"ref": "f"}}
        )

    install_mock(monkeypatch, handler)
    result = await pulls.update_pull_request("o", "r", 1, state="closed")
    assert captured["body"] == {"state": "closed"}
    assert result["state"] == "closed"


async def test_submit_pull_request_review_requires_body_for_changes(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await pulls.submit_pull_request_review("o", "r", 1, "REQUEST_CHANGES")
    assert exc.value.status_code == 400


async def test_request_reviewers_requires_one(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await pulls.request_pull_request_reviewers("o", "r", 5)
    assert exc.value.status_code == 400


async def test_request_reviewers(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/5/requested_reviewers"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"number": 5,
                                         "requested_reviewers": [{"login": "jd"}],
                                         "requested_teams": []})

    install_mock(monkeypatch, handler)
    result = await pulls.request_pull_request_reviewers("o", "r", 5,
                                                         reviewers=["jd"])
    assert captured["body"]["reviewers"] == ["jd"]
    assert result["requested_reviewers"] == ["jd"]


async def test_update_pull_request_branch(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/pulls/4/update-branch"
        return httpx.Response(202, json={"message": "Updating pull request branch."})

    install_mock(monkeypatch, handler)
    result = await pulls.update_pull_request_branch("o", "r", 4)
    assert result["updating"] is True
    assert "Updating" in result["message"]
