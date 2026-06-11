"""A Model Context Protocol (MCP) connector for GitHub.

Exposes a focused set of GitHub REST API operations as MCP tools so that
Claude (Desktop, Code, or any MCP client) can read repositories, issues,
pull requests, commits, and code, and optionally open issues and comments.
"""

# Importing these modules registers their @mcp.tool() functions on the shared
# FastMCP instance. `server` builds the instance and the bulk of the tools;
# `alerts` adds the per-alert security tools.
from . import server as server  # noqa: F401
from . import alerts as alerts  # noqa: F401

__version__ = "0.12.0"

__all__ = ["__version__", "server", "alerts"]
