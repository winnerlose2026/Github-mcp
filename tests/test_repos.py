"""Tests for github_mcp.repos."""

from __future__ import annotations

import json

import httpx
import pytest

from github_mcp import account, core, repos
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


async def test_get_rate_limit_filters_buckets(monkeypatch):
    def handler(request):
        assert request.url.path == "/rate_limit"
        return httpx.Response(200, json={"resources": {
            "core": {"limit": 5000, "remaining": 4999, "reset": 1},
            "search": {"limit": 30, "remaining": 30, "reset": 2},
            "graphql": {"limit": 5000, "remaining": 5000, "reset": 3},
            "code_search": {"limit": 10, "remaining": 10, "reset": 4}}})

    install_mock(monkeypatch, handler)
    result = await account.get_rate_limit()
    assert set(result) == {"core", "search", "graphql"}  # code_search dropped
    assert result["core"]["remaining"] == 4999


async def test_get_user(monkeypatch):
    def handler(request):
        assert request.url.path == "/users/octocat"
        return httpx.Response(200, json={"login": "octocat", "type": "User",
                                         "public_repos": 8, "extra": 1})

    install_mock(monkeypatch, handler)
    result = await account.get_user("octocat")
    assert result["login"] == "octocat"
    assert "extra" not in result


async def test_list_repository_languages(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/languages"
        return httpx.Response(200, json={"Python": 12345, "Shell": 67})

    install_mock(monkeypatch, handler)
    result = await repos.list_repository_languages("o", "r")
    assert result["Python"] == 12345


async def test_replace_repository_topics(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/topics"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"names": ["mcp", "github"]})

    install_mock(monkeypatch, handler)
    result = await repos.replace_repository_topics("o", "r", ["mcp", "github"])
    assert captured["body"] == {"names": ["mcp", "github"]}
    assert result["names"] == ["mcp", "github"]


async def test_update_repository_sends_only_set_fields(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"full_name": "o/r",
                                         "stargazers_count": 0})

    install_mock(monkeypatch, handler)
    await repos.update_repository("o", "r", description="new")
    assert captured["body"] == {"description": "new"}  # nothing else sent


async def test_create_commit_status(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/statuses/abc"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"state": "success", "context": "ci/x",
                                         "description": "ok", "target_url": None})

    install_mock(monkeypatch, handler)
    result = await repos.create_commit_status("o", "r", "abc", "success",
                                              context="ci/x", description="ok")
    assert captured["body"]["state"] == "success"
    assert result["context"] == "ci/x"


async def test_update_repository_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.update_repository("o", "r", description="x")
    assert exc.value.status_code == 403


async def test_list_my_repositories(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/user/repos"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, json=[{"full_name": "jd/a", "stargazers_count": 1}]
        )

    install_mock(monkeypatch, handler)
    result = await repos.list_my_repositories(sort="pushed", limit=5)
    assert result[0]["full_name"] == "jd/a"
    assert captured["params"]["sort"] == "pushed"
    assert captured["params"]["per_page"] == "5"


async def test_create_branch_resolves_sha_and_posts(monkeypatch):
    captured = {}

    def handler(request):
        import json
        if request.method == "GET" and request.url.path == "/repos/o/r/commits/main":
            return httpx.Response(200, json={"sha": "deadbeef"})
        if request.method == "POST" and request.url.path == "/repos/o/r/git/refs":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={"ref": "refs/heads/feature",
                      "object": {"sha": "deadbeef"}},
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    install_mock(monkeypatch, handler)
    result = await repos.create_branch("o", "r", "feature", from_ref="main")
    assert captured["body"] == {"ref": "refs/heads/feature", "sha": "deadbeef"}
    assert result["ref"] == "refs/heads/feature"
    assert result["sha"] == "deadbeef"


async def test_create_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.create_branch("o", "r", "feature", from_ref="main")
    assert exc.value.status_code == 403


async def test_delete_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.delete_branch("o", "r", "feature")
    assert exc.value.status_code == 403


async def test_delete_branch_calls_correct_ref(monkeypatch):
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await repos.delete_branch("o", "r", "feature-x")
    assert captured["method"] == "DELETE"
    assert captured["path"] == "/repos/o/r/git/refs/heads/feature-x"
    assert result == {"deleted": True, "branch": "feature-x"}


async def test_delete_branch_surfaces_api_error(monkeypatch):
    def handler(request):
        return httpx.Response(422, json={"message": "Reference does not exist"})

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await repos.delete_branch("o", "r", "missing")
    assert exc.value.status_code == 422


async def test_get_repository_tree_resolves_ref(monkeypatch):
    def handler(request):
        p = request.url.path
        if p == "/repos/o/r/commits/main":
            return httpx.Response(200, json={"commit": {"tree": {"sha": "t1"}}})
        if p == "/repos/o/r/git/trees/t1":
            assert request.url.params["recursive"] == "1"
            return httpx.Response(
                200,
                json={"sha": "t1", "truncated": False,
                      "tree": [{"path": "app.py", "type": "blob", "size": 5}]},
            )
        raise AssertionError(p)

    install_mock(monkeypatch, handler)
    result = await repos.get_repository_tree("o", "r", ref="main")
    assert result["sha"] == "t1"
    assert result["entries"][0]["path"] == "app.py"


async def test_find_reusable_repositories_builds_query(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/search/repositories"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"total_count": 1, "items": [{
                "full_name": "py-pdf/pypdf",
                "description": "pure-python PDF library",
                "stargazers_count": 7000,
                "language": "Python",
                "license": {"spdx_id": "BSD-3-Clause"},
                "topics": ["pdf", "python"],
                "pushed_at": "2026-05-01T00:00:00Z",
                "archived": False,
            }]},
        )

    install_mock(monkeypatch, handler)
    result = await repos.find_reusable_repositories(
        "parse pdf", language="python", min_stars=100, topic="pdf"
    )
    q = captured["params"]["q"]
    assert "parse pdf" in q
    assert "language:python" in q
    assert "topic:pdf" in q
    assert "stars:>=100" in q
    assert "archived:false" in q
    # defaults to ALL accessible repos, not just public
    assert "is:public" not in q
    assert captured["params"]["sort"] == "stars"
    assert result["query"] == q
    assert result["results"][0]["full_name"] == "py-pdf/pypdf"
    assert result["results"][0]["license"] == "BSD-3-Clause"


async def test_find_reusable_repositories_public_only_and_archived(monkeypatch):
    captured = {}

    def handler(request):
        captured["q"] = request.url.params["q"]
        return httpx.Response(200, json={"total_count": 0, "items": []})

    install_mock(monkeypatch, handler)
    await repos.find_reusable_repositories(
        "x", public_only=True, include_archived=True
    )
    assert "is:public" in captured["q"]
    assert "archived:false" not in captured["q"]


async def test_find_reusable_repositories_rejects_empty_query(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={"items": []}))
    with pytest.raises(GitHubError) as exc:
        await repos.find_reusable_repositories("   ")
    assert exc.value.status_code == 400


async def test_get_repository_tree_errors_without_default_branch(monkeypatch):
    def handler(request):
        if request.url.path == "/repos/o/r":
            return httpx.Response(200, json={})  # no default_branch
        raise AssertionError("should not reach commits/tree")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await repos.get_repository_tree("o", "r")
    assert exc.value.status_code == 404


async def test_create_repository_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.create_repository("newrepo")
    assert exc.value.status_code == 403


async def test_create_repository_user_and_org(monkeypatch):
    import json
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"full_name": "me/newrepo",
                                         "stargazers_count": 0})

    install_mock(monkeypatch, handler)
    await repos.create_repository("newrepo", description="d", auto_init=True)
    assert captured["path"] == "/user/repos"
    assert captured["body"]["auto_init"] is True

    await repos.create_repository("newrepo", org="acme")
    assert captured["path"] == "/orgs/acme/repos"


async def test_fork_repository(monkeypatch):
    import json
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/forks"
        captured["body"] = json.loads(request.content)
        return httpx.Response(202, json={"full_name": "me/r",
                                         "stargazers_count": 0})

    install_mock(monkeypatch, handler)
    result = await repos.fork_repository("o", "r", organization="acme")
    assert captured["body"]["organization"] == "acme"
    assert result["full_name"] == "me/r"


async def test_add_collaborator_puts_permission(monkeypatch):
    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/collaborators/alice"
        assert json.loads(request.content) == {"permission": "maintain"}
        return httpx.Response(201, json={"id": 77})

    install_mock(monkeypatch, handler)
    result = await repos.add_repository_collaborator("o", "r", "alice",
                                                          permission="maintain")
    assert result["added"] is True
    assert result["invitation_id"] == 77


async def test_add_collaborator_bad_permission(monkeypatch):
    def handler(request):  # pragma: no cover
        raise AssertionError("should not call API")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await repos.add_repository_collaborator("o", "r", "alice", "boss")
    assert exc.value.status_code == 422


async def test_remove_collaborator(monkeypatch):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/repos/o/r/collaborators/alice"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await repos.remove_repository_collaborator("o", "r", "alice")
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
    result = await repos.get_branch_protection("o", "r", "main")
    assert result["protected"] is True
    assert result["required_status_checks_contexts"] == ["CI"]
    assert result["enforce_admins"] is True
    assert result["required_approving_review_count"] == 1


async def test_get_branch_protection_unprotected(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(404, json={"message": "x"}))
    result = await repos.get_branch_protection("o", "r", "main")
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
    result = await repos.update_branch_protection(
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
    result = await repos.merge_branch("o", "r", "main", "feat")
    assert result["merged"] is True
    assert result["sha"] == "abc"


async def test_merge_branch_nothing_to_merge(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204))
    result = await repos.merge_branch("o", "r", "main", "feat")
    assert result["merged"] is False


async def test_merge_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await repos.merge_branch("o", "r", "main", "feat")
    assert exc.value.status_code == 403
