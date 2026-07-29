"""Tests for github_mcp.commits."""

from __future__ import annotations

import httpx

from github_mcp import commits, core
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
    result = await commits.get_commit("o", "r", "abc123")
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
    result = await commits.compare_commits("o", "r", "main", "feature")
    assert result["ahead_by"] == 2
    assert len(result["commits"]) == 1
    assert result["files"][0]["filename"] == "x"


async def test_get_combined_status(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/commits/main/status"
        return httpx.Response(
            200,
            json={"state": "success", "total_count": 1,
                  "statuses": [{"context": "ci", "state": "success"}]},
        )

    install_mock(monkeypatch, handler)
    result = await commits.get_combined_status("o", "r", "main")
    assert result["state"] == "success"
    assert result["statuses"][0]["context"] == "ci"


async def test_list_check_runs(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/commits/main/check-runs"
        return httpx.Response(
            200,
            json={"check_runs": [{"id": 1, "name": "Test", "status": "completed",
                                  "conclusion": "success"}]},
        )

    install_mock(monkeypatch, handler)
    result = await commits.list_check_runs("o", "r", "main")
    assert result[0]["conclusion"] == "success"
