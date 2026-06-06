"""Tests for the MCP tool functions, with the GitHub API mocked."""

import httpx
import pytest

from github_mcp import server
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the server's tools at a mocked GitHub API."""
    cfg = Config(
        token=token,
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(server, "config", cfg)
    monkeypatch.setattr(
        server,
        "GitHubClient",
        lambda c: GitHubClient(c, transport=transport),
    )


async def test_get_authenticated_user(monkeypatch):
    def handler(request):
        assert request.url.path == "/user"
        return httpx.Response(
            200, json={"login": "octocat", "name": "The Octocat", "public_repos": 8}
        )

    install_mock(monkeypatch, handler)
    result = await server.get_authenticated_user()
    assert result["login"] == "octocat"
    assert result["public_repos"] == 8


async def test_missing_token_raises(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}), token=None)
    with pytest.raises(GitHubError) as exc_info:
        await server.get_authenticated_user()
    assert exc_info.value.status_code == 401


async def test_search_repositories_summarizes(monkeypatch):
    def handler(request):
        assert request.url.path == "/search/repositories"
        assert request.url.params["q"] == "mcp"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "anthropics/mcp",
                        "description": "demo",
                        "stargazers_count": 42,
                        "extra_field": "ignored",
                    }
                ]
            },
        )

    install_mock(monkeypatch, handler)
    result = await server.search_repositories("mcp")
    assert len(result) == 1
    assert result[0]["full_name"] == "anthropics/mcp"
    assert result[0]["stars"] == 42
    assert "extra_field" not in result[0]


async def test_search_repositories_clamps_limit(monkeypatch):
    captured = {}

    def handler(request):
        captured["per_page"] = request.url.params["per_page"]
        return httpx.Response(200, json={"items": []})

    install_mock(monkeypatch, handler)
    await server.search_repositories("x", limit=999)
    assert captured["per_page"] == "50"


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
    result = await server.get_file_contents("o", "r", "README.md")
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
    result = await server.get_file_contents("o", "r", "src")
    assert result["type"] == "directory"
    assert len(result["entries"]) == 2


async def test_get_pull_request_diff_truncates(monkeypatch):
    big_diff = "x" * 100

    def handler(request):
        assert request.headers["Accept"] == "application/vnd.github.diff"
        return httpx.Response(200, text=big_diff)

    install_mock(monkeypatch, handler)
    result = await server.get_pull_request_diff("o", "r", 1, max_chars=10)
    assert result["truncated"] is True
    assert len(result["diff"]) == 10


async def test_create_issue_blocked_in_read_only(monkeypatch):
    install_mock(
        monkeypatch, lambda r: httpx.Response(200, json={}), read_only=True
    )
    with pytest.raises(GitHubError) as exc_info:
        await server.create_issue("o", "r", "title")
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
    result = await server.create_issue(
        "o", "r", "title", body="desc", labels=["bug"]
    )
    assert captured["body"] == {"title": "title", "body": "desc", "labels": ["bug"]}
    assert result["number"] == 7


# --- additional tools -------------------------------------------------------


async def test_list_my_repositories(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/user/repos"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, json=[{"full_name": "jd/a", "stargazers_count": 1}]
        )

    install_mock(monkeypatch, handler)
    result = await server.list_my_repositories(sort="pushed", limit=5)
    assert result[0]["full_name"] == "jd/a"
    assert captured["params"]["sort"] == "pushed"
    assert captured["params"]["per_page"] == "5"


async def test_get_commit_includes_files_and_stats(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/commits/abc123"
        return httpx.Response(
            200,
            json={
                "sha": "abc123",
                "commit": {"message": "fix", "author": {"name": "JD"}},
                "stats": {"total": 3, "additions": 2, "deletions": 1},
                "files": [
                    {"filename": "a.py", "status": "modified", "additions": 2,
                     "deletions": 1, "changes": 3}
                ],
            },
        )

    install_mock(monkeypatch, handler)
    result = await server.get_commit("o", "r", "abc123")
    assert result["sha"] == "abc123"
    assert result["stats"]["total"] == 3
    assert result["files"][0]["filename"] == "a.py"


async def test_compare_commits(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/compare/main...feature"
        return httpx.Response(
            200,
            json={
                "status": "ahead",
                "ahead_by": 2,
                "behind_by": 0,
                "total_commits": 2,
                "commits": [{"sha": "1", "commit": {"message": "m"}}],
                "files": [{"filename": "x", "status": "added"}],
            },
        )

    install_mock(monkeypatch, handler)
    result = await server.compare_commits("o", "r", "main", "feature")
    assert result["ahead_by"] == 2
    assert len(result["commits"]) == 1
    assert result["files"][0]["filename"] == "x"


async def test_list_workflow_runs_filters(monkeypatch):
    captured = {}

    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs"
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"workflow_runs": [
                {"id": 9, "name": "CI", "status": "completed",
                 "conclusion": "success"}
            ]},
        )

    install_mock(monkeypatch, handler)
    result = await server.list_workflow_runs("o", "r", branch="main",
                                             status="completed")
    assert result[0]["conclusion"] == "success"
    assert captured["params"]["branch"] == "main"
    assert captured["params"]["status"] == "completed"


async def test_list_releases(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/releases"
        return httpx.Response(
            200, json=[{"tag_name": "v1.0.0", "name": "v1", "draft": False}]
        )

    install_mock(monkeypatch, handler)
    result = await server.list_releases("o", "r")
    assert result[0]["tag_name"] == "v1.0.0"


async def test_update_issue_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.update_issue("o", "r", 1, state="closed")
    assert exc.value.status_code == 403


async def test_update_issue_requires_a_field(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubError) as exc:
        await server.update_issue("o", "r", 1)
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
    result = await server.update_issue("o", "r", 1, state="closed")
    assert captured["body"] == {"state": "closed"}
    assert result["state"] == "closed"


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
    result = await server.create_branch("o", "r", "feature", from_ref="main")
    assert captured["body"] == {"ref": "refs/heads/feature", "sha": "deadbeef"}
    assert result["ref"] == "refs/heads/feature"
    assert result["sha"] == "deadbeef"


async def test_create_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.create_branch("o", "r", "feature", from_ref="main")
    assert exc.value.status_code == 403


async def test_create_or_update_file_updates_existing(monkeypatch):
    import base64
    captured = {}

    def handler(request):
        import json
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
    result = await server.create_or_update_file(
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
        import json
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
    result = await server.create_or_update_file("o", "r", "new.md", "x", "add")
    assert "sha" not in captured["body"]  # no sha -> create
    assert result["created"] is True


async def test_delete_branch_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(204), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.delete_branch("o", "r", "feature")
    assert exc.value.status_code == 403


async def test_delete_branch_calls_correct_ref(monkeypatch):
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await server.delete_branch("o", "r", "feature-x")
    assert captured["method"] == "DELETE"
    assert captured["path"] == "/repos/o/r/git/refs/heads/feature-x"
    assert result == {"deleted": True, "branch": "feature-x"}


async def test_delete_branch_surfaces_api_error(monkeypatch):
    def handler(request):
        return httpx.Response(422, json={"message": "Reference does not exist"})

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await server.delete_branch("o", "r", "missing")
    assert exc.value.status_code == 422


async def test_create_pull_request_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.create_pull_request("o", "r", "t", "feature", "main")
    assert exc.value.status_code == 403


async def test_create_pull_request_posts_payload(monkeypatch):
    captured = {}

    def handler(request):
        import json
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
    result = await server.create_pull_request(
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
        await server.merge_pull_request("o", "r", 1)
    assert exc.value.status_code == 403


async def test_merge_pull_request_puts_payload(monkeypatch):
    captured = {}

    def handler(request):
        import json
        assert request.method == "PUT"
        assert request.url.path == "/repos/o/r/pulls/5/merge"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"merged": True, "sha": "abc", "message": "Pull Request successfully merged"}
        )

    install_mock(monkeypatch, handler)
    result = await server.merge_pull_request(
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
        await server.merge_pull_request("o", "r", 5)
    assert exc.value.status_code == 405


async def test_list_workflow_run_jobs_flags_failed_steps(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs/99/jobs"
        return httpx.Response(
            200,
            json={"jobs": [{
                "id": 5, "name": "Test", "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {"name": "setup", "conclusion": "success"},
                    {"name": "pytest", "conclusion": "failure"},
                ],
            }]},
        )

    install_mock(monkeypatch, handler)
    result = await server.list_workflow_run_jobs("o", "r", 99)
    assert result[0]["conclusion"] == "failure"
    assert result[0]["failed_steps"] == ["pytest"]


async def test_get_job_logs_tails(monkeypatch):
    log = "line\n" * 100  # 500 chars

    def handler(request):
        assert request.url.path == "/repos/o/r/actions/jobs/5/logs"
        return httpx.Response(200, text=log)

    install_mock(monkeypatch, handler)
    result = await server.get_job_logs("o", "r", 5, max_chars=20, tail=True)
    assert result["truncated"] is True
    assert len(result["logs"]) == 20
    assert result["logs"] == log[-20:]


async def test_list_pull_request_reviews(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/pulls/3/reviews"
        return httpx.Response(
            200,
            json=[{"id": 1, "user": {"login": "jd"}, "state": "APPROVED",
                   "body": "lgtm"}],
        )

    install_mock(monkeypatch, handler)
    result = await server.list_pull_request_reviews("o", "r", 3)
    assert result[0]["state"] == "APPROVED"
    assert result[0]["user"] == "jd"


async def test_list_secret_scanning_alerts_omits_secret(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/secret-scanning/alerts"
        return httpx.Response(
            200,
            json=[{"number": 1, "state": "open", "secret_type": "github_pat",
                   "secret": "ghp_SHOULD_NOT_LEAK", "html_url": "u"}],
        )

    install_mock(monkeypatch, handler)
    result = await server.list_secret_scanning_alerts("o", "r")
    assert result[0]["secret_type"] == "github_pat"
    assert "secret" not in result[0]
    assert "ghp_SHOULD_NOT_LEAK" not in str(result[0])


async def test_rerun_workflow_run_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(201), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.rerun_workflow_run("o", "r", 99)
    assert exc.value.status_code == 403


async def test_rerun_workflow_run_failed_only_endpoint(monkeypatch):
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(201, json={})

    install_mock(monkeypatch, handler)
    result = await server.rerun_workflow_run("o", "r", 99, failed_only=True)
    assert captured["method"] == "POST"
    assert captured["path"] == "/repos/o/r/actions/runs/99/rerun-failed-jobs"
    assert result == {"rerun": True, "run_id": 99, "failed_only": True}


async def test_create_release_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(201, json={}),
                 read_only=True)
    with pytest.raises(GitHubError) as exc:
        await server.create_release("o", "r", "v1.0.0")
    assert exc.value.status_code == 403


async def test_create_release_posts_payload(monkeypatch):
    captured = {}

    def handler(request):
        import json
        assert request.method == "POST"
        assert request.url.path == "/repos/o/r/releases"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"id": 99, "tag_name": "v1.0.0", "name": "v1.0.0",
                  "draft": False, "prerelease": False, "body": "notes",
                  "html_url": "u"},
        )

    install_mock(monkeypatch, handler)
    result = await server.create_release(
        "o", "r", "v1.0.0", target_commitish="main", name="v1.0.0",
        body="notes", generate_release_notes=True
    )
    assert captured["body"]["tag_name"] == "v1.0.0"
    assert captured["body"]["target_commitish"] == "main"
    assert captured["body"]["generate_release_notes"] is True
    assert captured["body"]["draft"] is False
    assert result["tag_name"] == "v1.0.0"
    assert result["id"] == 99
    assert result["body"] == "notes"


async def test_create_release_surfaces_existing_tag_error(monkeypatch):
    def handler(request):
        return httpx.Response(
            422, json={"message": "Validation Failed",
                       "errors": [{"code": "already_exists", "field": "tag_name"}]}
        )

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await server.create_release("o", "r", "v1.0.0")
    assert exc.value.status_code == 422
