"""A Model Context Protocol (MCP) connector for GitHub.

Exposes GitHub REST API operations as MCP tools so Claude (Desktop, Code,
or any MCP client) can read and act on repositories, issues, pull requests,
CI, releases, and security alerts.
"""

from __future__ import annotations

import importlib

from . import core as core  # noqa: F401
from . import summaries as summaries  # noqa: F401
from .config import TOOL_GROUPS, Config

# Importing a domain module is what registers its @mcp.tool() functions on the
# shared instance in `core`, so skipping one removes its tools from the server
# entirely. That is the point of GITHUB_MCP_TOOLS: a smaller tool list for
# clients that only need part of the surface. Default is every group.
_selected = Config.from_env().tool_groups or frozenset(TOOL_GROUPS)
for _group in TOOL_GROUPS:
    if _group in _selected:
        globals()[_group] = importlib.import_module(f".{_group}", __name__)

__version__ = "0.18.0"

__all__ = ["__version__", "core", "summaries", *sorted(_selected)]
