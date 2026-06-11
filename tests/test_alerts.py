"""Tests for the per-alert security tools in github_mcp.alerts."""

import json

import httpx
import pytest

from github_mcp import alerts, server
from github_mcp.client import GitHubClient, GitHubError
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


async def test_dismiss_dependabot_alert_patches_payload(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/dependabot/alerts/7"
        payload = json.loads(request.content)
        assert payload == {
            "state": "dismissed",
            "dismissed_reason": "tolerable_risk",
            "dismissed_comment": "Accepted for now.",
        }
        return httpx.Response(
            200,
            json={
                "number": 7,
                "state": "dismissed",
                "dismissed_reason": "tolerable_risk",
                "dismissed_comment": "Accepted for now.",
                "dismissed_at": "2026-06-10T00:00:00Z",
                "security_advisory": {"severity": "high", "summary": "x"},
                "dependency": {"package": {"name": "requests", "ecosystem": "pip"}},
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.dismiss_dependabot_alert(
        "o", "r", 7, "tolerable_risk", comment="Accepted for now."
    )
    assert result["state"] == "dismissed"
    assert result["dismissed_reason"] == "tolerable_risk"
    assert result["dismissed_comment"] == "Accepted for now."


async def test_dismiss_dependabot_alert_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await alerts.dismiss_dependabot_alert("o", "r", 7, "not_used")
    assert exc.value.status_code == 403


async def test_dismiss_dependabot_alert_rejects_bad_reason(monkeypatch):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("API should not be called for an invalid reason")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await alerts.dismiss_dependabot_alert("o", "r", 7, "because_i_said_so")
    assert exc.value.status_code == 422


async def test_dismiss_code_scanning_alert_patches_payload(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/code-scanning/alerts/3"
        payload = json.loads(request.content)
        assert payload == {
            "state": "dismissed",
            "dismissed_reason": "won't fix",
        }
        return httpx.Response(
            200,
            json={
                "number": 3,
                "state": "dismissed",
                "dismissed_reason": "won't fix",
                "dismissed_comment": None,
                "rule": {"id": "py/x", "security_severity_level": "medium"},
                "tool": {"name": "CodeQL"},
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.dismiss_code_scanning_alert("o", "r", 3, "won't fix")
    assert result["state"] == "dismissed"
    assert result["dismissed_reason"] == "won't fix"


async def test_resolve_secret_scanning_alert_patches_and_omits_secret(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/secret-scanning/alerts/5"
        payload = json.loads(request.content)
        assert payload == {
            "state": "resolved",
            "resolution": "revoked",
            "resolution_comment": "Rotated.",
        }
        return httpx.Response(
            200,
            json={
                "number": 5,
                "state": "resolved",
                "secret_type": "github_pat",
                "secret": "ghp_SHOULD_NOT_LEAK",
                "resolution": "revoked",
                "resolution_comment": "Rotated.",
                "resolved_at": "2026-06-10T00:00:00Z",
            },
        )

    install_mock(monkeypatch, handler)
    result = await alerts.resolve_secret_scanning_alert(
        "o", "r", 5, "revoked", comment="Rotated."
    )
    assert result["state"] == "resolved"
    assert result["resolution"] == "revoked"
    assert result["resolution_comment"] == "Rotated."
    assert "secret" not in result
    assert "ghp_SHOULD_NOT_LEAK" not in str(result)


async def test_resolve_secret_scanning_alert_rejects_bad_resolution(monkeypatch):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("API should not be called for an invalid resolution")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await alerts.resolve_secret_scanning_alert("o", "r", 5, "nah")
    assert exc.value.status_code == 422


# --- list_security_alerts (aggregate) --------------------------------------


async def test_list_security_alerts_combines_all_types(monkeypatch):
    def handler(request):
        p = request.url.path
        if p == "/repos/o/r/dependabot/alerts":
            return httpx.Response(200, json=[
                {"number": 7, "state": "open",
                 "security_advisory": {"severity": "high", "summary": "x"},
                 "dependency": {"package": {"name": "requests", "ecosystem": "pip"}}},
            ])
        if p == "/repos/o/r/code-scanning/alerts":
            return httpx.Response(200, json=[
                {"number": 3, "state": "open",
                 "rule": {"id": "py/x", "security_severity_level": "medium"},
                 "tool": {"name": "CodeQL"}},
            ])
        if p == "/repos/o/r/secret-scanning/alerts":
            return httpx.Response(200, json=[
                {"number": 5, "state": "open", "secret_type": "github_pat",
                 "secret": "ghp_SHOULD_NOT_LEAK"},
            ])
        raise AssertionError(f"unexpected path {p}")

    install_mock(monkeypatch, handler)
    result = await alerts.list_security_alerts("o", "r")
    assert result["counts"] == {
        "dependabot": 1, "code_scanning": 1, "secret_scanning": 1, "total": 3,
    }
    assert "errors" not in result
    assert "ghp_SHOULD_NOT_LEAK" not in str(result)


async def test_list_security_alerts_records_per_type_errors(monkeypatch):
    def handler(request):
        p = request.url.path
        if p == "/repos/o/r/dependabot/alerts":
            return httpx.Response(200, json=[{"number": 7, "state": "open",
                "security_advisory": {"severity": "low"}, "dependency": {}}])
        if p == "/repos/o/r/code-scanning/alerts":
            return httpx.Response(200, json=[])
        if p == "/repos/o/r/secret-scanning/alerts":
            return httpx.Response(403, json={"message": "no access"})
        raise AssertionError(f"unexpected path {p}")

    install_mock(monkeypatch, handler)
    result = await alerts.list_security_alerts("o", "r")
    assert result["counts"]["total"] == 1
    assert "secret_scanning" in result["errors"]
    assert result["secret_scanning"] == []


# --- create_issues_for_alerts (automation) ---------------------------------


async def test_create_issues_for_alerts_creates_and_dedups(monkeypatch):
    posted = []
    counter = {"n": 100}

    def handler(request):
        p = request.url.path
        m = request.method
        if m == "GET" and p == "/repos/o/r/dependabot/alerts":
            return httpx.Response(200, json=[{"number": 7, "state": "open",
                "security_advisory": {"severity": "critical", "summary": "RCE"},
                "dependency": {"package": {"name": "requests", "ecosystem": "pip"}}}])
        if m == "GET" and p == "/repos/o/r/code-scanning/alerts":
            return httpx.Response(200, json=[{"number": 3, "state": "open",
                "rule": {"id": "py/x", "security_severity_level": "high"},
                "tool": {"name": "CodeQL"}}])
        if m == "GET" and p == "/repos/o/r/secret-scanning/alerts":
            return httpx.Response(200, json=[{"number": 5, "state": "open",
                "secret_type": "github_pat",
                "secret_type_display_name": "GitHub PAT"}])
        if m == "GET" and p == "/repos/o/r/issues":
            # dependabot#7 already tracked
            return httpx.Response(200, json=[
                {"number": 1, "title": "[security:dependabot#7] old"},
            ])
        if m == "POST" and p == "/repos/o/r/issues":
            payload = json.loads(request.content)
            posted.append(payload)
            counter["n"] += 1
            return httpx.Response(201, json={
                "number": counter["n"],
                "html_url": f"https://github.com/o/r/issues/{counter['n']}",
            })
        raise AssertionError(f"unexpected {m} {p}")

    install_mock(monkeypatch, handler)
    result = await alerts.create_issues_for_alerts("o", "r")
    assert result["counts"] == {"created": 2, "skipped": 1, "alerts_seen": 3}
    assert result["skipped_existing"] == ["security:dependabot#7"]
    created_markers = sorted(c["alert"] for c in result["created"])
    assert created_markers == ["security:code-scanning#3", "security:secret-scanning#5"]
    # every created issue carries the security label and its marker in the body
    assert all(pl["labels"] == ["security"] for pl in posted)
    assert any("security:code-scanning#3" in pl["title"] for pl in posted)
    assert all("<!-- security:" in pl["body"] for pl in posted)


async def test_create_issues_for_alerts_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await alerts.create_issues_for_alerts("o", "r")
    assert exc.value.status_code == 403


async def test_create_issues_for_alerts_rejects_bad_type(monkeypatch):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("API should not be called for invalid alert_types")

    install_mock(monkeypatch, handler)
    with pytest.raises(GitHubError) as exc:
        await alerts.create_issues_for_alerts("o", "r", alert_types=["bogus"])
    assert exc.value.status_code == 422
