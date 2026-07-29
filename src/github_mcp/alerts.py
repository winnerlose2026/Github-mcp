"""Security alerts: Dependabot, code scanning, and secret scanning.

Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;
the package ``__init__`` imports this module to register them.
"""

from __future__ import annotations

import re
from typing import Any

from .client import GitHubError
from .core import _clamp, _session, mcp
from .summaries import (
    _summarize_code_scanning_alert,
    _summarize_dependabot_alert,
    _summarize_secret_alert,
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


_ALERT_TYPES = ("dependabot", "code_scanning", "secret_scanning")


_ALERT_SPECS = {
    "dependabot": ("dependabot/alerts", _summarize_dependabot_alert, "dependabot"),
    "code_scanning": (
        "code-scanning/alerts",
        _summarize_code_scanning_alert,
        "code-scanning",
    ),
    "secret_scanning": (
        "secret-scanning/alerts",
        _summarize_secret_alert,
        "secret-scanning",
    ),
}


_MARKER_RE = re.compile(r"\[(security:[a-z0-9._-]+#\d+)\]")


def _validate_alert_types(alert_types: list[str] | None) -> list[str]:
    if not alert_types:
        return list(_ALERT_TYPES)
    bad = [t for t in alert_types if t not in _ALERT_TYPES]
    if bad:
        raise GitHubError(
            422,
            "GET",
            "",
            f"Invalid alert_types {bad}. Must be a subset of {list(_ALERT_TYPES)}.",
        )
    # Preserve caller order but drop duplicates.
    seen: dict[str, None] = {}
    for t in alert_types:
        seen.setdefault(t, None)
    return list(seen)


async def _collect_alerts(
    gh, owner: str, repo: str, types: list[str], state: str, limit: int
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Fetch summarized alerts for each type, tolerating per-type failures.

    A type that errors (e.g. the feature is disabled or the token lacks the
    permission) is recorded in `errors` rather than failing the whole call.
    """
    collected: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for t in types:
        path_seg, summarizer, _slug = _ALERT_SPECS[t]
        try:
            raw = await gh.get(
                f"/repos/{owner}/{repo}/{path_seg}",
                params={"state": state, "per_page": limit},
            )
            collected[t] = [summarizer(a) for a in raw]
        except GitHubError as exc:
            errors[t] = exc.detail or str(exc)
    return collected, errors


@mcp.tool()
async def list_security_alerts(
    owner: str, repo: str, state: str = "open", limit: int = 30
) -> dict[str, Any]:
    """List Dependabot, code-scanning, and secret-scanning alerts in one call.

    Returns the three alert lists keyed by type plus a `counts` block. `state`
    is passed to each endpoint (`open` (default) or `all` are valid for all
    three); `limit` (max 100) is the per-type cap. If a type can't be read
    (feature disabled, or the token lacks that permission), it's reported under
    `errors` instead of failing the whole call. The secret value of
    secret-scanning alerts is never returned.
    """
    limit = _clamp(limit, 100)
    types = list(_ALERT_TYPES)
    async with _session() as gh:
        collected, errors = await _collect_alerts(
            gh, owner, repo, types, state, limit
        )
    result: dict[str, Any] = {
        "dependabot": collected.get("dependabot", []),
        "code_scanning": collected.get("code_scanning", []),
        "secret_scanning": collected.get("secret_scanning", []),
    }
    counts = {t: len(collected.get(t, [])) for t in _ALERT_TYPES}
    counts["total"] = sum(counts[t] for t in _ALERT_TYPES)
    result["counts"] = counts
    if errors:
        result["errors"] = errors
    return result


def _issue_for_alert(alert_type: str, alert: dict[str, Any]) -> tuple[str, str, str]:
    """Build the (marker, title, body) for the tracking issue of one alert."""
    slug = _ALERT_SPECS[alert_type][2]
    number = alert.get("number")
    marker = f"security:{slug}#{number}"
    url = alert.get("html_url")
    if alert_type == "dependabot":
        sev = alert.get("severity") or "unknown"
        pkg = alert.get("package")
        eco = alert.get("ecosystem")
        summary = alert.get("summary") or "Dependabot alert"
        title = f"[{marker}] {sev}: {pkg} ({eco}) — {summary}"
        detail = (
            f"- Package: `{pkg}` ({eco})\n"
            f"- Severity: {sev}\n"
            f"- Summary: {summary}"
        )
    elif alert_type == "code_scanning":
        sev = alert.get("severity") or "unknown"
        rule = alert.get("rule_id") or "code-scanning alert"
        desc = alert.get("description")
        tool = alert.get("tool")
        title = f"[{marker}] {sev}: {rule}"
        detail = (
            f"- Rule: `{rule}`\n"
            f"- Severity: {sev}\n"
            f"- Tool: {tool}\n"
            f"- Description: {desc}"
        )
    else:  # secret_scanning
        stype = alert.get("secret_type_display_name") or alert.get("secret_type")
        title = f"[{marker}] Secret detected: {stype}"
        detail = f"- Secret type: {stype}\n- State: {alert.get('state')}"
    title = title[:240]
    body = (
        "Security alert tracked from GitHub.\n\n"
        f"{detail}\n"
        f"- Link: {url}\n\n"
        f"<!-- {marker} -->\n"
        "_Opened automatically by github-mcp `create_issues_for_alerts`. "
        "The marker in the title is used to avoid duplicates._"
    )
    return marker, title, body


async def _existing_alert_markers(gh, owner: str, repo: str) -> set[str]:
    """Markers already tracked by `security`-labeled issues (open or closed)."""
    issues = await gh.get(
        f"/repos/{owner}/{repo}/issues",
        params={"state": "all", "labels": "security", "per_page": 100},
    )
    markers: set[str] = set()
    for it in issues:
        if "pull_request" in it:
            continue
        markers.update(_MARKER_RE.findall(it.get("title") or ""))
    return markers


@mcp.tool()
async def create_issues_for_alerts(
    owner: str,
    repo: str,
    alert_types: list[str] | None = None,
    state: str = "open",
    limit: int = 30,
) -> dict[str, Any]:
    """Open a tracking issue for each open security alert (a gated write).

    For every alert of the requested types (default: all of `dependabot`,
    `code_scanning`, `secret_scanning`), this opens a GitHub issue titled
    `[security:<type>#<number>] …` and labeled `security`, unless an issue with
    that marker already exists. Existing issues are detected among the repo's
    `security`-labeled issues (open or closed), so re-running is safe and won't
    create duplicates. `limit` (max 100) caps how many alerts per type are
    considered. A type that can't be read is reported under `errors`.

    Returns `created` (alert marker + new issue number/url), `skipped_existing`,
    any per-type `errors`, and `counts`. This is a write tool — disabled in
    read-only mode — and may open multiple issues in one call.
    """
    types = _validate_alert_types(alert_types)
    limit = _clamp(limit, 100)
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    async with _session(write=True) as gh:
        collected, errors = await _collect_alerts(
            gh, owner, repo, types, state, limit
        )
        existing = await _existing_alert_markers(gh, owner, repo)
        seen = 0
        for t in types:
            for alert in collected.get(t, []):
                seen += 1
                marker, title, body = _issue_for_alert(t, alert)
                if marker in existing:
                    skipped.append(marker)
                    continue
                issue = await gh.post(
                    f"/repos/{owner}/{repo}/issues",
                    json={"title": title, "body": body, "labels": ["security"]},
                )
                created.append(
                    {
                        "alert": marker,
                        "issue_number": issue.get("number"),
                        "issue_url": issue.get("html_url"),
                    }
                )
                existing.add(marker)  # guard against duplicates within this run
    result: dict[str, Any] = {
        "created": created,
        "skipped_existing": skipped,
        "counts": {
            "created": len(created),
            "skipped": len(skipped),
            "alerts_seen": seen,
        },
    }
    if errors:
        result["errors"] = errors
    return result


@mcp.tool()
async def list_secret_scanning_alerts(
    owner: str, repo: str, state: str = "open", limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List secret-scanning alerts for a repository (the Security tab).

    `state` is `open` (default), `resolved`, or `all`. The raw secret value is
    never returned — only the type, state, and resolution. Requires a token with
    access to security alerts (repo admin / `security_events`); GitHub returns
    403/404 otherwise. Returns up to `limit` (max 100) alerts.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        alerts = await gh.get(
            f"/repos/{owner}/{repo}/secret-scanning/alerts",
            params={"state": state, "per_page": limit, "page": page},
        )
    return [_summarize_secret_alert(a) for a in alerts]


@mcp.tool()
async def list_code_scanning_alerts(
    owner: str, repo: str, state: str = "open", limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List code-scanning (CodeQL etc.) alerts for a repository.

    `state` is `open` (default), `dismissed`, `fixed`, or `all`. Returns each
    alert's rule, severity, and tool. Requires a token with access to security
    alerts. Returns up to `limit` (max 100) alerts.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        alerts = await gh.get(
            f"/repos/{owner}/{repo}/code-scanning/alerts",
            params={"state": state, "per_page": limit, "page": page},
        )
    return [_summarize_code_scanning_alert(a) for a in alerts]


@mcp.tool()
async def list_dependabot_alerts(
    owner: str, repo: str, state: str = "open", limit: int = 30,
    page: int = 1,
) -> list[dict[str, Any]]:
    """List Dependabot (vulnerable-dependency) alerts for a repository.

    `state` is `open` (default), `dismissed`, `fixed`, `auto_dismissed`, or
    `all`. Returns the affected package, severity, and advisory summary. Requires
    a token with access to security alerts. Returns up to `limit` (max 100)
    alerts.

    Paginated: returns at most `limit` items from page `page` (1-based). If you
    get exactly `limit` items there are probably more; request `page=2`, and so
    on.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        alerts = await gh.get(
            f"/repos/{owner}/{repo}/dependabot/alerts",
            params={"state": state, "per_page": limit, "page": page},
        )
    return [_summarize_dependabot_alert(a) for a in alerts]
