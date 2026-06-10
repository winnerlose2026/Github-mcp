# GitHub MCP Connector

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
connects **Claude** to **GitHub**. It exposes 50+ GitHub REST API operations as
MCP tools, so Claude (Desktop, Code, or any MCP client) can search and read
repositories, files, and commit history; triage and comment on issues; review,
open, and merge pull requests; drive CI (read logs, re-run, dispatch); inspect
security alerts; and—optionally—make changes (open/merge PRs, submit reviews,
manage labels/assignees, commit files, cut releases). Every write is gated by a
single read-only switch.

It's a small, dependency-light Python package (`mcp` + `httpx`) that you point
at a GitHub token. It supports both stdio (the default for Claude Desktop/Code)
and streamable HTTP transports, and works against github.com or GitHub
Enterprise Server.

## Features

- 🔍 **Search & discover** repositories, issues, PRs, commits, code, and users — plus find reusable repos (across everything your token can see, license/activity-aware) for what you're building
- 📦 **Repositories** — metadata, branches, tags, file contents, directory listings, your repo list; create and fork repos
- 🧾 **Commits** — history, single-commit detail, and diffs between refs
- 🐛 **Issues** — list, read, create, comment, read comments, edit/close, label, assign
- 🔀 **Pull requests** — list, read, diffs/files, comments, open, update, merge, and review
- ⚙️ **Actions & releases** — list runs/jobs, read failed-job logs, re-run/dispatch/**schedule** workflows, commit statuses & check runs, list/create releases
- 🔐 **Security** — secret-scanning, code-scanning, and Dependabot alerts (list, fetch one by number, and dismiss/resolve)
- 🔔 **Notifications** — list and mark read across all your repos
- ✍️ **Repo writes** — create/fork repos, create branches, commit/delete files, manage labels (create/edit/delete) & assignees, request PR reviewers, create/edit gists (gated by read-only mode)
- 🔒 **Read-only mode** — flip one env var to disable every write tool
- 🏢 **Enterprise-friendly** — set `GITHUB_API_URL` for GitHub Enterprise Server

## Tools

| Tool | Description | Write |
|------|-------------|:-----:|
| `get_authenticated_user` | Identity/health check for the configured token | |
| `list_my_repositories` | List repos the token can access | |
| `search_repositories` | Search repositories by query | |
| `get_repository` | Repository metadata | |
| `get_repository_tree` | Recursive file tree at a ref | |
| `list_branches` | Branches with head commit SHAs | |
| `get_file_contents` | Read a file (decoded) or list a directory | |
| `list_commits` | Recent commits, optional branch/path filter | |
| `get_commit` | A single commit with stats and changed files | |
| `compare_commits` | Diff/ahead-behind between two refs | |
| `get_combined_status` | Combined commit status for a ref | |
| `list_check_runs` | Check runs for a ref | |
| `list_issues` | Issues by state/labels | |
| `get_issue` | A single issue with full body | |
| `list_issue_comments` | Conversation comments on an issue/PR | |
| `list_pull_requests` | Pull requests by state | |
| `get_pull_request` | A single PR with body and merge status | |
| `get_pull_request_diff` | Unified diff for a PR (truncated) | |
| `list_pull_request_files` | Files changed in a PR | |
| `list_pull_request_reviews` | Reviews submitted on a PR | |
| `list_pull_request_review_comments` | Inline code-review comments on a PR | |
| `list_workflow_runs` | Recent GitHub Actions runs | |
| `list_workflow_run_jobs` | Jobs in a run (flags failed steps) | |
| `get_job_logs` | Plain-text logs for a job (tail) | |
| `list_releases` | Releases for a repository | |
| `list_notifications` | Your notifications across all repos | |
| `list_secret_scanning_alerts` | Secret-scanning alerts (no secret values) | |
| `list_code_scanning_alerts` | Code-scanning (CodeQL) alerts | |
| `list_dependabot_alerts` | Dependabot vulnerability alerts | |
| `get_secret_scanning_alert` | A single secret-scanning alert by number (no secret value) | |
| `get_code_scanning_alert` | A single code-scanning alert by number, with instance location | |
| `get_dependabot_alert` | A single Dependabot alert by number, with full advisory detail | |
| `search_issues` | Search issues and PRs across GitHub | |
| `search_pull_requests` | Search PRs across GitHub (auto-adds `is:pr`) | |
| `search_commits` | Search commits across GitHub | |
| `search_users` | Search users and organizations | |
| `search_code` | Search code across GitHub | |
| `list_labels` | Labels defined in a repository | |
| `list_tags` | Git tags with their commit SHAs | |
| `get_tag` | Resolve a tag to its commit | |
| `list_gists` | The authenticated user's gists | |
| `get_latest_release` | A repository's latest published release | |
| `get_release_by_tag` | A specific release by tag (incl. drafts) | |
| `get_gist` | A single gist with file contents | |
| `find_reusable_repositories` | Find reusable repos for what you're building (license/activity-aware; public + accessible private) | |
| `create_pull_request` | Open a new pull request (supports draft) | ✅ |
| `update_pull_request` | Edit title/body/base, close/reopen a PR | ✅ |
| `merge_pull_request` | Merge a PR (merge/squash/rebase) | ✅ |
| `submit_pull_request_review` | Approve / request changes / comment | ✅ |
| `add_pull_request_review_comment` | Inline comment on a PR diff line | ✅ |
| `rerun_workflow_run` | Re-run a workflow run (or just failed jobs) | ✅ |
| `trigger_workflow` | Dispatch a workflow_dispatch run | ✅ |
| `create_scheduled_workflow` | Commit a cron-scheduled workflow ("do X later") | ✅ |
| `create_release` | Create a release (and its tag) | ✅ |
| `create_issue` | Open a new issue | ✅ |
| `update_issue` | Edit/close/reopen an issue | ✅ |
| `add_issue_comment` | Comment on an issue or PR | ✅ |
| `add_labels` | Add labels to an issue/PR | ✅ |
| `remove_label` | Remove a label from an issue/PR | ✅ |
| `add_assignees` | Assign users to an issue/PR | ✅ |
| `mark_notification_read` | Mark a notification thread read | ✅ |
| `create_branch` | Create a branch from a ref | ✅ |
| `delete_branch` | Delete a branch | ✅ |
| `create_or_update_file` | Commit a file (create or update) | ✅ |
| `delete_file` | Delete a file in a single commit | ✅ |
| `create_gist` | Create a (secret or public) gist | ✅ |
| `update_gist` | Edit a gist's files/description | ✅ |
| `create_repository` | Create a new repo (user or org) | ✅ |
| `fork_repository` | Fork a repo to your account/an org | ✅ |
| `create_label` | Create a label in a repository | ✅ |
| `update_label` | Edit/rename a label | ✅ |
| `delete_label` | Delete a label | ✅ |
| `request_pull_request_reviewers` | Request user/team reviews on a PR | ✅ |
| `dismiss_dependabot_alert` | Dismiss a Dependabot alert (with reason) | ✅ |
| `dismiss_code_scanning_alert` | Dismiss a code-scanning alert (with reason) | ✅ |
| `resolve_secret_scanning_alert` | Resolve a secret-scanning alert (with resolution) | ✅ |

Tools marked **Write** are disabled when `GITHUB_MCP_READ_ONLY` is set.

## Requirements

- Python 3.10+
- A GitHub personal access token. The connector applies **no repository
  restrictions of its own** — it can reach exactly the repositories your token
  can, so token scope is what controls access:
  - **All your repositories (recommended for general use):** create a *classic*
    PAT with the `repo` scope, or a *fine-grained* PAT whose "Repository access"
    is set to **All repositories**. This lets the connector see every repo your
    account can access (public and private).
  - **Only specific repositories:** use a fine-grained PAT and select just those
    repos under "Repository access".
  - **Permissions:** read access is enough for the read tools. The write tools
    need scopes matching what they touch — for a classic PAT the `repo` scope
    covers most (issues, PRs, reviews, labels, assignees, branches, files,
    releases, statuses), `workflow` is required for `trigger_workflow` /
    `rerun_workflow_run`, and `gist` for `create_gist`. Fine-grained tokens need
    the corresponding per-resource "Read and write" permissions (Contents,
    Issues, Pull requests, Actions, etc.), and security-alert tools require the
    relevant code-scanning/Dependabot/secret-scanning alert read permissions.

## Install from PyPI (recommended)

The connector is published to PyPI as
[`github-mcp-connector`](https://pypi.org/project/github-mcp-connector/), so you
can install or run it by name — no clone, no git, no build step. This is the
most reliable option on Windows, where launching from a git URL requires Git on
the spawned process's `PATH`.

```bash
uvx github-mcp-connector            # run on demand with uv (nothing to install)
pipx run github-mcp-connector       # same, with pipx
pip install github-mcp-connector    # or install it permanently
```

Wire it into Claude by pointing the command at the published package:

**Claude Code:**
```bash
claude mcp add-json github '{
  "command": "uvx",
  "args": ["github-mcp-connector"],
  "env": { "GITHUB_TOKEN": "github_pat_your_token_here" }
}'
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "github": {
      "command": "uvx",
      "args": ["github-mcp-connector"],
      "env": { "GITHUB_TOKEN": "github_pat_your_token_here" }
    }
  }
}
```

On Windows, use the full path to `uvx.exe` (run `where.exe uvx` to find it), e.g.
`C:\\Users\\you\\.local\\bin\\uvx.exe`.

## Quick start (no clone, no venv)

If the package isn't published yet (or you want to track an unreleased commit),
`uvx` can also fetch, build, and run the connector straight from GitHub. This
path requires Git to be available to the process that launches it.

**Claude Code — one command:**

```bash
claude mcp add-json github '{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/winnerlose2026/Github-mcp.git", "github-mcp"],
  "env": { "GITHUB_TOKEN": "github_pat_your_token_here" }
}'
```

Add `--scope user` to make it available in every project. Verify with
`claude mcp list` (should show `github` connected).

**Claude Code — project-scoped, shareable:** this repo ships a [`.mcp.json`](.mcp.json)
that reads `GITHUB_TOKEN` from your environment. Drop the same file in any project
(or copy it from here), export your token, and Claude Code auto-detects it:

```bash
export GITHUB_TOKEN=github_pat_your_token_here
claude   # prompts once to approve the project MCP server
```

**Claude Desktop:** point the `command` at `uvx` so there's no interpreter path to
manage:

```json
{
  "mcpServers": {
    "github": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/winnerlose2026/Github-mcp.git", "github-mcp"],
      "env": { "GITHUB_TOKEN": "github_pat_your_token_here" }
    }
  }
}
```

**Prefer pipx?** `pipx run --spec git+https://github.com/winnerlose2026/Github-mcp.git github-mcp`
works the same way; use that as the `command`/`args` instead.

## Installation (from source)

For development, or if you don't use `uv`/`pipx`:

```bash
git clone https://github.com/winnerlose2026/Github-mcp.git
cd Github-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Or, without installing, from the repo root:

```bash
pip install -r requirements.txt
python -m github_mcp
```

## Configuration

All configuration comes from environment variables (see [`.env.example`](.env.example)):

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `GITHUB_TOKEN` | yes | — | GitHub token. `GITHUB_PERSONAL_ACCESS_TOKEN` and `GH_TOKEN` are also accepted. |
| `GITHUB_API_URL` | no | `https://api.github.com` | API root; set for GitHub Enterprise Server (e.g. `https://ghe.example.com/api/v3`). |
| `GITHUB_MCP_READ_ONLY` | no | `false` | When truthy, disables all write tools. |
| `GITHUB_MCP_TIMEOUT` | no | `30` | Per-request timeout in seconds. |
| `GITHUB_MCP_USER_AGENT` | no | `github-mcp-connector` | `User-Agent` header sent to GitHub. |

## Connecting to Claude (from-source install)

If you installed from source (above) instead of using `uvx`/`pipx`, configure
the client to run the package directly.

### Claude Desktop

Add the server to `claude_desktop_config.json` (Settings → Developer → Edit
Config):

```json
{
  "mcpServers": {
    "github": {
      "command": "python",
      "args": ["-m", "github_mcp"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

Use the absolute path to the Python interpreter from the virtualenv where you
installed the package (e.g. `/path/to/Github-mcp/.venv/bin/python`), or the
`github-mcp` console script directly. Restart Claude Desktop after editing.

### Claude Code

```bash
claude mcp add github \
  --env GITHUB_TOKEN=ghp_your_token_here \
  -- python -m github_mcp
```

### Streamable HTTP

To run as a standalone HTTP server instead of stdio:

```bash
GITHUB_TOKEN=ghp_your_token_here python -m github_mcp --http
```

## Example prompts

Once connected, you can ask Claude things like:

- "What's the open PR backlog on `owner/repo`?"
- "Read `README.md` from the default branch of `owner/repo` and summarize it."
- "Show me the diff for PR #42 and summarize the risky parts."
- "Open an issue titled 'Flaky test in CI' with these reproduction steps…"

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite mocks the GitHub API with `httpx.MockTransport`, so it runs
fully offline and makes no network calls.

## Releasing (maintainers)

Publishing is automated via GitHub Actions
([`.github/workflows/publish.yml`](.github/workflows/publish.yml)) using PyPI
**Trusted Publishing** (OIDC) — no API tokens are stored anywhere.

**One-time PyPI setup** (before the first release):

1. Sign in at [pypi.org](https://pypi.org) and go to **Your projects → Publishing**
   (or **Account → Publishing** for a project that doesn't exist yet).
2. Add a **pending publisher** with:
   - PyPI Project Name: `github-mcp-connector`
   - Owner: `winnerlose2026`
   - Repository: `Github-mcp`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. (Recommended) In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments) so the publish job is gated.

**Cutting a release:**

1. Bump `version` in `pyproject.toml`, commit, and merge to `main`.
2. Tag and publish a GitHub Release (e.g. `v0.1.0`). Publishing the release
   triggers the workflow, which builds the sdist + wheel, runs `twine check`,
   and uploads to PyPI.
3. Confirm it's live: `uvx github-mcp-connector@latest --help`.

Until the first release is published, install via the
[git-based quick start](#quick-start-no-clone-no-venv) instead.

## Security notes

- The connector only has the access your token grants. A broad token (`repo`
  scope / all repositories) gives Claude reach across every repo your account
  can touch — convenient, but treat the token like the credential it is. Prefer
  a fine-grained, repo-limited token if you only need a few repositories.
- Run with `GITHUB_MCP_READ_ONLY=true` when you only need read access; this is
  enforced server-side, before any write request is sent to GitHub. This pairs
  well with a broad-access token: full visibility, no write risk.
- Never commit your token. `.env` is git-ignored; `.env.example` is the
  template to copy.

## License

[MIT](LICENSE)
