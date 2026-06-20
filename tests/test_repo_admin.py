"""Tests for github_mcp.repo_admin."""

import json

import httpx
import pytest

from github_mcp import repo_admin, server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    cfg = Config(token=token, api_url="https://api.github.com",
                 read_only=read_only, timeout=5.0, user_agent="t")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(server, "GitHubClient",
                        lambda c: GitHubClient(c, transport=transport))


async def test_add_collaborator_puts_permission(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/collaborators/alice"
        assert json.loads(request.content) == {"permission": "maintain"}
        return httpx.Response(201, json={"id": 77})

    install_mock(monkeypatch, handler)
    result = await repo_admin.add_repository_collaborator("o", "r", "alice",
                                                          permission="maintain")
    assert result["added"] is True
    assert result["invitation_id"] == 77


async def test_add_collaborator_bad_permission(monkeypatch):
    def handler(request):  # pragma: no cover
        raise AssertionError("should not call API")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await repo_admin.add_repository_collaborator("o", "r", "alice", "boss")
    assert exc.value.status_code == 422


async def test_remove_collaborator(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/collaborators/alice"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await repo_admin.remove_repository_collaborator("o", "r", "alice")
    assert result == {"removed": True, "username": "alice"}


async def test_get_branch_protection_summary(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/branches/main/protection"
        return httpx.Response(200, json={
            "required_status_checks": {"strict": True, "contexts": ["CI"]},
            "enforce_admins": {"enabled": True},
            "required_pull_request_reviews": {"required_approving_review_count": 1,
                                              "require_code_owner_reviews": False}})

    install_mock(monkeypatch, handler)
    result = await repo_admin.get_branch_protection("o", "r", "main")
    assert result["protected"] is True
    assert result["required_status_checks_contexts"] == ["CI"]
    assert result["enforce_admins"] is True
    assert result["required_approving_review_count"] == 1


async def test_get_branch_protection_unprotected(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(404, json={"message": "x"}))
    result = await repo_admin.get_branch_protection("o", "r", "main")
    assert result == {"protected": False, "branch": "main"}


async def test_update_branch_protection_body(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/branches/main/protection"
        body = json.loads(request.content)
        assert body["required_status_checks"] == {"strict": True, "contexts": ["CI"]}
        assert body["enforce_admins"] is True
        assert body["required_pull_request_reviews"][
            "required_approving_review_count"] == 2
        assert "restrictions" in body
        return httpx.Response(200, json={})

    install_mock(monkeypatch, handler)
    result = await repo_admin.update_branch_protection(
        "o", "r", "main", required_status_check_contexts=["CI"],
        enforce_admins=True, required_approving_review_count=2)
    assert result == {"updated": True, "branch": "main"}


async def test_merge_branch_creates_commit(monkeypatch):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/merges"
        assert json.loads(request.content) == {"base": "main", "head": "feat"}
        return httpx.Response(201, json={"sha": "abc", "html_url": "u"})

    install_mock(monkeypatch, handler)
    result = await repo_admin.merge_branch("o", "r", "main", "feat")
    assert result["merged"] is True
    assert result["sha"] == "abc"


async def test_merge_branch_nothing_to_merge(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204))
    result = await repo_admin.merge_branch("o", "r", "main", "feat")
    assert result["merged"] is False


async def test_merge_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repo_admin.merge_branch("o", "r", "main", "feat")
    assert exc.value.status_code == 403
