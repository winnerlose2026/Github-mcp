"""Tests for the per-alert security tools in github_mcp.alerts."""

import httpx

from github_mcp import alerts, server
from github_mcp.client import GitHubClient
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the server's session at a mocked GitHub API.

    The per-alert tools call `server._session`, which reads `server.config` and
    `server.GitHubClient`, so those are what we patch.
    """
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


async def test_get_dependabot_alert_includes_advisory_detail(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/dependabot/alerts/7"
        return httpx.Response(
            200,
            json={
                "number": 7,
                "state": "open",
                "security_advisory": {
                    "severity": "critical",
                    "summary": "RCE",
                    "description": "A remote code execution flaw.",
                    "ghsa_id": "GHSA-xxxx",
                    "cve_id": "CVE-2026-0001",
                    "cvss": {"score": 9.8},
                    "references": [{"url": "https://example.com/advisory"}],
                },
                "security_vulnerability": {
                    "vulnerable_version_range": "< 2.0.0",
                    "first_patched_version": {"identifier": "2.0.0"},
                },
                "dependency": {
                    "package": {"name": "requests", "ecosystem": "pip"},
                    "manifest_path": "requirements.txt",
                    "scope": "runtime",
                },
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.get_dependabot_alert("o", "r", 7)
    assert result["number"] == 7
    assert result["package"] == "requests"
    assert result["cve_id"] == "CVE-2026-0001"
    assert result["cvss_score"] == 9.8
    assert result["first_patched_version"] == "2.0.0"
    assert result["references"] == ["https://example.com/advisory"]


async def test_get_code_scanning_alert_includes_instance(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/code-scanning/alerts/3"
        return httpx.Response(
            200,
            json={
                "number": 3,
                "state": "open",
                "rule": {
                    "id": "py/sql-injection",
                    "name": "py/sql-injection",
                    "security_severity_level": "high",
                    "description": "SQL injection",
                    "full_description": "Building a SQL query from user input.",
                    "help_uri": "https://example.com/help",
                },
                "tool": {"name": "CodeQL", "version": "2.16.0"},
                "most_recent_instance": {
                    "ref": "refs/heads/main",
                    "message": {"text": "This query depends on user input."},
                    "location": {
                        "path": "app/db.py",
                        "start_line": 42,
                        "end_line": 42,
                    },
                },
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.get_code_scanning_alert("o", "r", 3)
    assert result["severity"] == "high"
    assert result["tool_version"] == "2.16.0"
    assert result["location"]["path"] == "app/db.py"
    assert result["location"]["start_line"] == 42
    assert result["ref"] == "refs/heads/main"


async def test_get_secret_scanning_alert_omits_secret(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/secret-scanning/alerts/5"
        return httpx.Response(
            200,
            json={
                "number": 5,
                "state": "resolved",
                "secret_type": "github_pat",
                "secret_type_display_name": "GitHub Personal Access Token",
                "secret": "ghp_SHOULD_NOT_LEAK",
                "resolution": "revoked",
                "resolution_comment": "Rotated the token.",
                "push_protection_bypassed": False,
                "validity": "active",
                "html_url": "u",
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.get_secret_scanning_alert("o", "r", 5)
    assert result["number"] == 5
    assert result["resolution"] == "revoked"
    assert result["resolution_comment"] == "Rotated the token."
    assert result["validity"] == "active"
    assert "secret" not in result
    assert "ghp_SHOULD_NOT_LEAK" not in str(result)
