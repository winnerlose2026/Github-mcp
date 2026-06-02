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
- A GitHub personal access token (classic or fine-grained). Scope it to only
  the repositories and permissions you want the connector to have. For
  read-only use, read access to the relevant repositories is enough; to use the
  write tools the token also needs issue write access.

## Quick start (no clone, no venv)

If you have [`uv`](https://docs.astral.sh/uv/) installed, `uvx` can fetch, build,
and run the connector straight from GitHub — there's nothing to clone or install.
Just have a `GITHUB_TOKEN` ready.

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

- "What's the open PR backlog on `winnerlose2026/inventory-tracker`?"
- "Read `render.yaml` from the default branch and explain the cron jobs."
- "Show me the diff for PR #42 and summarize the risky parts."
- "Open an issue titled 'Flaky USF report parse' with these reproduction steps…"

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite mocks the GitHub API with `httpx.MockTransport`, so it runs
fully offline and makes no network calls.

## Security notes

- The connector only has the access your token grants—scope tokens narrowly.
- Run with `GITHUB_MCP_READ_ONLY=true` when you only need read access; this is
  enforced server-side, before any write request is sent to GitHub.
- Never commit your token. `.env` is git-ignored; `.env.example` is the
  template to copy.

## License

[MIT](LICENSE)
