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


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    token: str | None
    api_url: str
    read_only: bool
    timeout: float
    user_agent: str

    @classmethod
    def from_env(cls) -> "Config":
        api_url = os.environ.get("GITHUB_API_URL", DEFAULT_API_URL).rstrip("/")
        timeout_raw = os.environ.get("GITHUB_MCP_TIMEOUT", "30")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 30.0
        return cls(
            token=_read_token(),
            api_url=api_url,
            read_only=_read_bool("GITHUB_MCP_READ_ONLY", default=False),
            timeout=timeout,
            user_agent=os.environ.get("GITHUB_MCP_USER_AGENT", "github-mcp-connector"),
        )
