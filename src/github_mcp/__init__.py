"""A Model Context Protocol (MCP) connector for GitHub.

Exposes a focused set of GitHub REST API operations as MCP tools so that
Claude (Desktop, Code, or any MCP client) can read repositories, issues,
pull requests, commits, and code, and optionally open issues and comments.
"""

# Importing these modules registers their @mcp.tool() functions on the shared
# FastMCP instance. `server` builds the instance and the bulk of the tools; the
# remaining modules add focused groups: `alerts` (per-alert security), `releases`
# (release/tag editing & assets), `actions` (workflow definitions & cancel),
# `repos` (metadata/collaborators/topics/status), `issues` (milestones, locking,
# PR commits), `deployments` (environment approval gates), `actions_config`
# (Actions secrets/variables/artifacts), `repo_admin` (collaborator & branch
# protection writes, branch merges), and `extras` (PR-branch sync, comment
# edits, release-asset and gist deletes, notifications).
# The import order here is alphabetical (enforced by ruff) and does not
# matter: each module does `from .server import mcp`, so importing any of
# them initializes `server` and the shared instance first.
from . import actions as actions  # noqa: F401
from . import actions_config as actions_config  # noqa: F401
from . import alerts as alerts  # noqa: F401
from . import deployments as deployments  # noqa: F401
from . import extras as extras  # noqa: F401
from . import issues as issues  # noqa: F401
from . import releases as releases  # noqa: F401
from . import repo_admin as repo_admin  # noqa: F401
from . import repos as repos  # noqa: F401
from . import server as server  # noqa: F401

__version__ = "0.16.0"

__all__ = [
    "__version__",
    "server",
    "alerts",
    "releases",
    "actions",
    "repos",
    "issues",
    "deployments",
    "actions_config",
    "repo_admin",
    "extras",
]
