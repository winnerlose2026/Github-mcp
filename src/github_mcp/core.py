"""Shared foundation for every tool module.

Holds the FastMCP instance, the resolved configuration, and the auth and
session plumbing every tool runs through. Tool modules import from here;
nothing here imports them, so there are no cycles.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .client import GitHubClient, GitHubError
from .config import Config

config = Config.from_env()


INSTRUCTIONS = """\
This server connects Claude to GitHub via the REST API.

Use it to look up repositories, read files and commit history, triage issues,
and review pull requests. Always pass `owner` and `repo` separately (for the
repo `octocat/hello-world`, owner is `octocat` and repo is `hello-world`).

For free-text discovery use the `search_*` tools, which accept GitHub search
qualifiers (e.g. `repo:owner/name`, `is:open`, `label:bug`, `language:python`).
"""


mcp = FastMCP("github", instructions=INSTRUCTIONS)


def _require_token() -> None:
    if not config.token:
        raise GitHubError(
            401,
            "AUTH",
            config.api_url,
            "No GitHub token configured. Set GITHUB_TOKEN (or "
            "GITHUB_PERSONAL_ACCESS_TOKEN) in the connector environment.",
        )


def _require_write() -> None:
    if config.read_only:
        raise GitHubError(
            403,
            "WRITE",
            config.api_url,
            "This connector is running in read-only mode "
            "(GITHUB_MCP_READ_ONLY is set); write operations are disabled.",
        )


def _clamp(limit: int, ceiling: int = 100) -> int:
    """Clamp a caller-supplied `limit` into the 1..ceiling range GitHub accepts."""
    return max(1, min(limit, ceiling))


@asynccontextmanager
async def _session(*, write: bool = False):
    """Enforce auth, then yield a GitHub client.

    Every tool runs through this: it requires a configured token, additionally
    requires write access when `write=True`, and opens (and cleanly closes) a
    :class:`GitHubClient`. Centralizes the auth policy that used to be repeated
    at the top of each tool.
    """
    _require_token()
    if write:
        _require_write()
    async with GitHubClient(config) as gh:
        yield gh
