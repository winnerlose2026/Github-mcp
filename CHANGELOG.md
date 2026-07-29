# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/); the project is pre-1.0, so minor
bumps may add sizeable batches of tools.

## [0.17.0] — 2026-07-29

### Changed
- **`server.py` split into domain modules.** It had grown to 2,074 lines doing two
  unrelated jobs: holding the package's shared foundation *and* acting as a
  70-tool grab bag that nine sibling modules reached into. Now:
  - `core.py` — the FastMCP instance, resolved config, and the auth/session
    plumbing every tool runs through. Nothing in it imports a tool module, so
    there are no cycles.
  - `summaries.py` — the 16 response-shaping helpers.
  - Tools live in modules named for their domain: `account`, `search`, `repos`,
    `files`, `commits`, `issues`, `pulls`, `actions`, `actions_config`,
    `releases`, `alerts`, `gists`, `notifications`, `deployments`.
  - `server.py` is now just the console entry point (34 lines).
- **Dissolved the `extras.py` and `repo_admin.py` junk drawers**; their tools moved
  to the domain they belong to.
- Tests mirror the new layout — `test_server.py` was split the same way, and
  `install_mock` now patches `core` (where `_session` lives).

Purely a move: **the tool surface is byte-identical**. All 122 tools keep the same
names, descriptions, and input schemas — asserted by comparing a SHA-256
fingerprint of the full tool list before and after
(`c5f84390cb200f41b5ab0df90cab0c43a57d0a5045cfff0c49625bfbe7db8d90`). No action
needed by users of the connector.

## [0.16.0] — 2026-07-29

### Fixed
- **Pinned `mcp` to `<2`.** The `mcp` SDK 2.0.0 (released 2026-07-28) removed
  `mcp.server.fastmcp`, which this package imports. Because the dependency was
  declared as `mcp>=1.2.0` with no upper bound, every *fresh* install — including
  `uvx`, which resolves on each launch — began failing at import with
  `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. This affected all
  previously published versions, so downgrading the connector did not help.
- `httpx` and `pynacl` given upper bounds (`<1`, `<2`) for the same reason.
- `requirements.txt` was missing `pynacl` (added in 0.15.0) and carried the same
  unbounded `mcp` range, so the documented from-source install was broken. It now
  mirrors `[project.dependencies]`.
- Corrected a stale `.env.example` comment that described read-only mode as
  disabling only `create_issue` / `add_issue_comment`.

### Added
- Nightly scheduled CI run (plus `workflow_dispatch`). Dependency resolution
  happens at install time, so an upstream breaking release can break users
  without any commit here; the schedule catches it.
- `scripts/smoke_stdio.py` and a CI **smoke** job (Ubuntu + Windows) that builds
  the wheel, installs it, launches `python -m github_mcp`, and completes a real
  MCP `initialize` + `tools/list` handshake. Unit tests import the package
  in-process and would not have caught the 2.0 breakage; this does.
- `ruff` lint configuration and a CI lint job.
- `.github/dependabot.yml` for weekly pip and github-actions updates.
- `tests/test_registry.py`: guards that tool names are unique, every tool has a
  description and input schema, and the README tool table matches the registered
  tools exactly (in both directions).
- `py.typed` marker so downstream consumers get the package's type hints.

## [0.15.0] — 2026-06-20

### Added
- Deployment gates: `list_pending_deployments`, `review_deployment` — approve or
  reject a workflow run's pending environment deployments.
- Actions configuration: `list_repo_secrets`, `set_repo_secret` (values sealed
  client-side with the repo public key; never read back), `delete_repo_secret`,
  `list_repo_variables`, `set_repo_variable`, `delete_repo_variable`,
  `list_run_artifacts`, `download_artifact`.
- Repository administration: `add_repository_collaborator`,
  `remove_repository_collaborator`, `get_branch_protection`,
  `update_branch_protection`, `merge_branch`.
- CRUD gaps: `update_pull_request_branch`, `update_issue_comment`,
  `delete_issue_comment`, `delete_release_asset`, `download_release_asset`,
  `delete_gist`, `mark_all_notifications_read`.
- New dependency `pynacl`, required to encrypt Actions secret values.

## [0.14.0] — 2026-06-19

### Added
- Milestones (`create_milestone`, `list_milestones`), issue locking
  (`lock_issue`, `unlock_issue`), `list_pull_request_commits`.
- Repository metadata: `update_repository`, `get_repository_topics`,
  `replace_repository_topics`, `list_repository_languages`,
  `list_repository_collaborators`.
- Releases: `update_release`, `generate_release_notes`, `list_release_assets`,
  `upload_release_asset`.
- Actions/CI: `list_workflows`, `cancel_workflow_run`, `create_commit_status`.
- Account/diagnostics: `get_user`, `get_rate_limit`.

## [0.13.0] — 2026-06-11

### Added
- `delete_release`, `delete_tag`, and `delete_release_and_tag` (a release and its
  git tag are separate objects; the combined tool tolerates either being absent).

## [0.12.0] — 2026-06-11

### Added
- `list_security_alerts` — Dependabot, code-scanning, and secret-scanning alerts
  in one call, tolerating per-type read failures.
- `create_issues_for_alerts` — opens a `security`-labeled tracking issue per open
  alert, deduplicated by a `[security:<type>#<number>]` title marker.

## [0.11.0] — 2026-06-10

### Added
- Per-alert security tools: `get_dependabot_alert`, `get_code_scanning_alert`,
  `get_secret_scanning_alert`, `dismiss_dependabot_alert`,
  `dismiss_code_scanning_alert`, `resolve_secret_scanning_alert`.

## [0.1.0] – [0.10.0]

Initial development: the core connector (repositories, files, commits, issues,
pull requests, reviews, Actions, releases, search, gists, notifications, and
security-alert listing), read-only mode, PyPI publishing via Trusted Publishing,
and packaging/install improvements. See the GitHub releases for details.
