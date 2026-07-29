"""A Model Context Protocol (MCP) connector for GitHub.

Exposes GitHub REST API operations as MCP tools so Claude (Desktop, Code,
or any MCP client) can read and act on repositories, issues, pull requests,
CI, releases, and security alerts.
"""

# `core` builds the shared FastMCP instance; importing each domain module
# registers its @mcp.tool() functions on it. Import order is irrelevant:
# every module takes the instance from `core`.
from . import account as account  # noqa: F401
from . import actions as actions  # noqa: F401
from . import actions_config as actions_config  # noqa: F401
from . import alerts as alerts  # noqa: F401
from . import commits as commits  # noqa: F401
from . import core as core  # noqa: F401
from . import deployments as deployments  # noqa: F401
from . import files as files  # noqa: F401
from . import gists as gists  # noqa: F401
from . import issues as issues  # noqa: F401
from . import notifications as notifications  # noqa: F401
from . import pulls as pulls  # noqa: F401
from . import releases as releases  # noqa: F401
from . import repos as repos  # noqa: F401
from . import search as search  # noqa: F401
from . import summaries as summaries  # noqa: F401

__version__ = "0.18.0"

__all__ = [
    "__version__",
    "core",
    "summaries",
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
]
