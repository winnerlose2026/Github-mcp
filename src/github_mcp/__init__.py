"""A Model Context Protocol (MCP) connector for GitHub.

Exposes a focused set of GitHub REST API operations as MCP tools so that
Claude (Desktop, Code, or any MCP client) can read repositories, issues,
pull requests, commits, and code, and optionally open issues and comments.
"""

# Importing these modules registers their @mcp.tool() functions on the shared
# FastMCP instance. `server` builds the instance and the bulk of the tools; the
# remaining modules add focused groups: `alerts` (per-alert security), `releases`
# (release/tag editing & assets), `actions` (workflow definitions & cancel),
# `repos` (metadata/collaborators/topics/status), and `issues` (milestones,
# locking, PR commits).
from . import server as server  # noqa: F401
from . import alerts as alerts  # noqa: F401
from . import releases as releases  # noqa: F401
from . import actions as actions  # noqa: F401
from . import repos as repos  # noqa: F401
from . import issues as issues  # noqa: F401

__version__ = "0.14.0"

__all__ = [
    "__version__",
    "server",
    "alerts",
    "releases",
    "actions",
    "repos",
    "issues",
]
