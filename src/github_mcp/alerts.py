"""Per-alert (single-alert) GitHub security tools.

These complement the bulk ``list_*_alerts`` tools in :mod:`github_mcp.server`.
The ``get_*`` tools fetch one alert's full detail by its per-repository
``alert_number`` (the number shown by the corresponding list tool); the
``dismiss_*`` / ``resolve_*`` tools act on a single alert and are writes, so
they are disabled in read-only mode. All register on the same FastMCP instance
and reuse the server's auth/session and summarizers, so they honor the same
token and read-only policy. The package ``__init__`` imports this module for
the side effect of registering these tools.
"""

from __future__ import annotations

from typing import Any

from .client import GitHubError
from .server import (
    _session,
    _summarize_code_scanning_alert,
    _summarize_dependabot_alert,
    _summarize_secret_alert,
    mcp,
)


@mcp.tool()
async def get_dependabot_alert(
    owner: str, repo: str, alert_number: int
) -> dict[str, Any]:
    """Get a single Dependabot alert by its number, with full advisory detail.

    Where `list_dependabot_alerts` returns a one-line summary per alert, this
    returns one alert's complete detail: the advisory description, CVE/GHSA
    identifiers and CVSS score, the vulnerable version range and first patched
    version, the affected manifest, and advisory reference links. `alert_number`
    is the per-repository number shown by the list tool (not a global id).
    Requires a token with access to security alerts.
    """
    async with _session() as gh:
        alert = await gh.get(
            f"/repos/{owner}/{repo}/dependabot/alerts/{alert_number}"
        )
    advisory = alert.get("security_advisory") or {}
    vuln = alert.get("security_vulnerability") or {}
    dependency = alert.get("dependency") or {}
    summary = _summarize_dependabot_alert(alert)
    summary.update(
        {
            "ghsa_id": advisory.get("ghsa_id"),
            "cve_id": advisory.get("cve_id"),
            "cvss_score": (advisory.get("cvss") or {}).get("score"),
            "description": advisory.get("description"),
            "vulnerable_version_range": vuln.get("vulnerable_version_range"),
            "first_patched_version": (
                vuln.get("first_patched_version") or {}
            ).get("identifier"),
            "manifest_path": dependency.get("manifest_path"),
            "scope": dependency.get("scope"),
            "dismissed_reason": alert.get("dismissed_reason"),
            "references": [r.get("url") for r in advisory.get("references", [])],
            "updated_at": alert.get("updated_at"),
        }
    )
    return summary


@mcp.tool()
async def get_code_scanning_alert(
    owner: str, repo: str, alert_number: int
) -> dict[str, Any]:
    """Get a single code-scanning (CodeQL etc.) alert by its number.

    Where `list_code_scanning_alerts` returns a one-line summary per alert, this
    returns one alert's full detail: the rule's full description and help URI,
    the analysis tool and version, and the most recent instance (file path, line
    range, ref, and the alert message). `alert_number` is the per-repository
    number shown by the list tool. Requires a token with access to security
    alerts.
    """
    async with _session() as gh:
        alert = await gh.get(
            f"/repos/{owner}/{repo}/code-scanning/alerts/{alert_number}"
        )
    rule = alert.get("rule") or {}
    tool = alert.get("tool") or {}
    instance = alert.get("most_recent_instance") or {}
    location = instance.get("location") or {}
    summary = _summarize_code_scanning_alert(alert)
    summary.update(
        {
            "rule_name": rule.get("name"),
            "rule_description": rule.get("full_description")
            or rule.get("description"),
            "rule_help_uri": rule.get("help_uri"),
            "tool_version": tool.get("version"),
            "message": (instance.get("message") or {}).get("text"),
            "location": {
                "path": location.get("path"),
                "start_line": location.get("start_line"),
                "end_line": location.get("end_line"),
            },
            "ref": instance.get("ref"),
            "dismissed_reason": alert.get("dismissed_reason"),
            "dismissed_comment": alert.get("dismissed_comment"),
            "updated_at": alert.get("updated_at"),
        }
    )
    return summary


@mcp.tool()
async def get_secret_scanning_alert(
    owner: str, repo: str, alert_number: int
) -> dict[str, Any]:
    """Get a single secret-scanning alert by its number.

    Where `list_secret_scanning_alerts` returns a one-line summary per alert,
    this returns one alert's full detail: its resolution and resolution comment,
    whether push protection was bypassed, and the secret's validity. As with the
    list tool, the raw secret value is never returned. `alert_number` is the
    per-repository number shown by the list tool. Requires a token with access
    to security alerts (repo admin / `security_events`).
    """
    async with _session() as gh:
        alert = await gh.get(
            f"/repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}"
        )
    summary = _summarize_secret_alert(alert)
    summary.update(
        {
            "validity": alert.get("validity"),
            "push_protection_bypassed": alert.get("push_protection_bypassed"),
            "resolution_comment": alert.get("resolution_comment"),
            "resolved_at": alert.get("resolved_at"),
            "updated_at": alert.get("updated_at"),
        }
    )
    return summary


# Allowed dismissal/resolution reasons per GitHub's API. Validated client-side
# so an invalid value fails fast with a clear message instead of a raw 422.
_DEPENDABOT_DISMISS_REASONS = {
    "fix_started",
    "inaccurate",
    "no_bandwidth",
    "not_used",
    "tolerable_risk",
}
_CODE_SCANNING_DISMISS_REASONS = {"false positive", "won't fix", "used in tests"}
_SECRET_SCANNING_RESOLUTIONS = {
    "false_positive",
    "wont_fix",
    "revoked",
    "used_in_tests",
}


@mcp.tool()
async def dismiss_dependabot_alert(
    owner: str,
    repo: str,
    alert_number: int,
    reason: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Dismiss an open Dependabot alert (a write; gated by read-only mode).

    `reason` must be one of: `fix_started`, `inaccurate`, `no_bandwidth`,
    `not_used`, `tolerable_risk`. `comment` is an optional free-text note stored
    with the dismissal. `alert_number` is the per-repository number shown by
    `list_dependabot_alerts`. Requires a token with write access to Dependabot
    alerts.
    """
    path = f"/repos/{owner}/{repo}/dependabot/alerts/{alert_number}"
    if reason not in _DEPENDABOT_DISMISS_REASONS:
        raise GitHubError(
            422,
            "PATCH",
            path,
            f"Invalid reason '{reason}'. Must be one of: "
            f"{', '.join(sorted(_DEPENDABOT_DISMISS_REASONS))}.",
        )
    payload: dict[str, Any] = {"state": "dismissed", "dismissed_reason": reason}
    if comment is not None:
        payload["dismissed_comment"] = comment
    async with _session(write=True) as gh:
        alert = await gh.patch(path, json=payload)
    summary = _summarize_dependabot_alert(alert)
    summary.update(
        {
            "dismissed_reason": alert.get("dismissed_reason"),
            "dismissed_comment": alert.get("dismissed_comment"),
            "dismissed_at": alert.get("dismissed_at"),
        }
    )
    return summary


@mcp.tool()
async def dismiss_code_scanning_alert(
    owner: str,
    repo: str,
    alert_number: int,
    reason: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Dismiss an open code-scanning alert (a write; gated by read-only mode).

    `reason` must be one of GitHub's exact values: `false positive`,
    `won't fix`, `used in tests`. `comment` is an optional note (max 280
    characters). `alert_number` is the per-repository number shown by
    `list_code_scanning_alerts`. Requires a token with write access to
    code-scanning alerts.
    """
    path = f"/repos/{owner}/{repo}/code-scanning/alerts/{alert_number}"
    if reason not in _CODE_SCANNING_DISMISS_REASONS:
        raise GitHubError(
            422,
            "PATCH",
            path,
            f"Invalid reason '{reason}'. Must be one of: "
            f"{', '.join(sorted(_CODE_SCANNING_DISMISS_REASONS))}.",
        )
    payload: dict[str, Any] = {"state": "dismissed", "dismissed_reason": reason}
    if comment is not None:
        payload["dismissed_comment"] = comment
    async with _session(write=True) as gh:
        alert = await gh.patch(path, json=payload)
    summary = _summarize_code_scanning_alert(alert)
    summary.update(
        {
            "dismissed_reason": alert.get("dismissed_reason"),
            "dismissed_comment": alert.get("dismissed_comment"),
            "dismissed_at": alert.get("dismissed_at"),
        }
    )
    return summary


@mcp.tool()
async def resolve_secret_scanning_alert(
    owner: str,
    repo: str,
    alert_number: int,
    resolution: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Resolve (close) an open secret-scanning alert (a gated write).

    `resolution` must be one of: `false_positive`, `wont_fix`, `revoked`,
    `used_in_tests`. `comment` is an optional resolution note. The raw secret is
    never returned. `alert_number` is the per-repository number shown by
    `list_secret_scanning_alerts`. Requires a token with write access to
    secret-scanning alerts.
    """
    path = f"/repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}"
    if resolution not in _SECRET_SCANNING_RESOLUTIONS:
        raise GitHubError(
            422,
            "PATCH",
            path,
            f"Invalid resolution '{resolution}'. Must be one of: "
            f"{', '.join(sorted(_SECRET_SCANNING_RESOLUTIONS))}.",
        )
    payload: dict[str, Any] = {"state": "resolved", "resolution": resolution}
    if comment is not None:
        payload["resolution_comment"] = comment
    async with _session(write=True) as gh:
        alert = await gh.patch(path, json=payload)
    summary = _summarize_secret_alert(alert)
    summary.update(
        {
            "resolution_comment": alert.get("resolution_comment"),
            "resolved_at": alert.get("resolved_at"),
        }
    )
    return summary
