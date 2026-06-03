# GitHub MCP Connector

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
connects **Claude** to **GitHub**. It exposes a focused set of GitHub REST API
operations as MCP tools, so Claude (Desktop, Code, or any MCP client) can read
repositories, browse files and commit history, triage issues, review pull
requests, and—optionally—open issues and post comments.

It's a small, dependency-light Python package (`mcp` + `httpx`) that you point
at a GitHub token. It supports both stdio (the default for Claude Desktop/Code)
and streamable HTTP transports, and works against github.com or GitHub
Enterprise Server.

## Features

- 🔍 **Search** repositories, issues/PRs, and code with GitHub's query syntax
- 📦 **Repositories** — metadata, branches, file contents, directory listings
- 🧾 **Commits** — recent history, optionally filtered to a branch or file path
- 🐛 **Issues** — list, read, and (optionally) create issues and comments
- 🔀 **Pull requests** — list, read, and fetch unified diffs
- 🔒 **Read-only mode** — flip one env var to disable every write tool
- 🏢 **Enterprise-friendly** — set `GITHUB_API_URL` for GitHub Enterprise Server

## Tools

| Tool | Description | Write |
|------|-------------|:-----:|
| `get_authenticated_user` | Identity/health check for the configured token | |
| `search_repositories` | Search repositories by query | |
| `get_repository` | Repository metadata | |
| `list_branches` | Branches with head commit SHAs | |
| `get_file_contents` | Read a file (decoded) or list a directory | |
| `list_commits` | Recent commits, optional branch/path filter | |
| `list_issues` | Issues by state/labels | |
| `get_issue` | A single issue with full body | |
| `list_pull_requests` | Pull requests by state | |
| `get_pull_request` | A single PR with body and merge status | |
| `get_pull_request_diff` | Unified diff for a PR (truncated) | |
| `search_issues` | Search issues and PRs across GitHub | |
| `search_code` | Search code across GitHub | |
| `create_issue` | Open a new issue | ✅ |
| `add_issue_comment` | Comment on an issue or PR | ✅ |

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
  - **Permissions:** read access is enough for the read tools; to use the write
    tools (`create_issue`, `add_issue_comment`) the token also needs issue
    write access (classic: `repo`; fine-grained: *Issues → Read and write*).

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
