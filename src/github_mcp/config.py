"""Configuration for the GitHub MCP connector.

All configuration is read from environment variables so the server can be
launched by an MCP client (Claude Desktop/Code) with nothing but an ``env``
block. See ``.env.example`` for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_API_URL = "https://api.github.com"

# Environment variable names, in priority order, that may hold the token.
_TOKEN_ENV_VARS = (
    "GITHUB_TOKEN",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GH_TOKEN",
)


def _read_token() -> str | None:
    for name in _TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return None


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Domain modules selectable with GITHUB_MCP_TOOLS. `core` and `summaries` are
# infrastructure and always loaded.
TOOL_GROUPS = (
    "account",
    "actions",
    "actions_config",
    "alerts",
    "commits",
    "deployments",
    "files",
    "gists",
    "issues",
    "notifications",
    "pulls",
    "releases",
    "repos",
    "search",
)


def _read_tool_groups() -> frozenset[str] | None:
    """Parse GITHUB_MCP_TOOLS into module names, or None meaning "all".

    Loading only the groups you need trims the tool list every client session
    carries. An unknown name is a hard error rather than a silent no-op, because
    quietly exposing nothing looks like a broken connector.
    """
    raw = os.environ.get("GITHUB_MCP_TOOLS", "").strip()
    if not raw:
        return None
    wanted = {part.strip() for part in raw.replace(",", " ").split() if part.strip()}
    unknown = sorted(wanted - set(TOOL_GROUPS))
    if unknown:
        raise ValueError(
            f"GITHUB_MCP_TOOLS names unknown tool group(s): {', '.join(unknown)}. "
            f"Valid groups: {', '.join(TOOL_GROUPS)}."
        )
    return frozenset(wanted)


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    token: str | None
    api_url: str
    read_only: bool
    timeout: float
    user_agent: str
    # Defaulted so callers (and tests) predating these can omit them.
    max_retries: int = 3
    tool_groups: frozenset[str] | None = None

    @classmethod
    def from_env(cls) -> Config:
        api_url = os.environ.get("GITHUB_API_URL", DEFAULT_API_URL).rstrip("/")
        timeout_raw = os.environ.get("GITHUB_MCP_TIMEOUT", "30")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 30.0
        retries_raw = os.environ.get("GITHUB_MCP_MAX_RETRIES", "3")
        try:
            max_retries = max(0, int(retries_raw))
        except ValueError:
            max_retries = 3
        return cls(
            token=_read_token(),
            api_url=api_url,
            read_only=_read_bool("GITHUB_MCP_READ_ONLY", default=False),
            timeout=timeout,
            user_agent=os.environ.get("GITHUB_MCP_USER_AGENT", "github-mcp-connector"),
            max_retries=max_retries,
            tool_groups=_read_tool_groups(),
        )
