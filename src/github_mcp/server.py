"""Console entry point.

The tools live in the domain modules imported by the package
``__init__``; this module only parses CLI arguments and starts the
shared FastMCP instance::

    python -m github_mcp            # stdio (Claude Desktop/Code)
    python -m github_mcp --http     # streamable HTTP
"""

from __future__ import annotations

# Importing the package registers every tool on the shared instance.
import github_mcp  # noqa: F401

from .core import mcp


def main(argv: list[str] | None = None) -> None:
    """Console entry point. Selects the transport from CLI args/env."""
    import argparse

    parser = argparse.ArgumentParser(prog="github-mcp", description=__doc__)
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over streamable HTTP instead of stdio.",
    )
    args = parser.parse_args(argv)
    mcp.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
