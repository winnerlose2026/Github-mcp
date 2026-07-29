"""Guards on the tool registry itself.

These don't exercise the GitHub API; they protect properties that are easy to
break silently as modules are added — duplicate tool names (a later
registration would shadow an earlier one), missing descriptions (the docstring
*is* what the model sees when choosing a tool), and README drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from github_mcp import server

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture(scope="module")
async def tools():
    return await server.mcp.list_tools()


async def test_tool_names_are_unique(tools):
    names = [t.name for t in tools]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate tool names would shadow each other: {duplicates}"


async def test_every_tool_has_a_description(tools):
    missing = [t.name for t in tools if not (t.description or "").strip()]
    assert not missing, f"tools missing a docstring/description: {missing}"


async def test_every_tool_has_an_input_schema(tools):
    bad = [t.name for t in tools if not isinstance(t.inputSchema, dict)]
    assert not bad, f"tools with no input schema: {bad}"


async def test_readme_documents_every_registered_tool(tools):
    """The README's tool table must list exactly the registered tools.

    Catches both directions of drift: a new tool that was never documented, and
    a table row left behind after a rename or removal.
    """
    documented = set(re.findall(r"^\| `([a-z0-9_]+)` \|", README.read_text(encoding="utf-8"), re.M))
    registered = {t.name for t in tools}
    undocumented = registered - documented
    stale = documented - registered
    assert not undocumented, f"tools missing from the README table: {sorted(undocumented)}"
    assert not stale, f"README lists tools that no longer exist: {sorted(stale)}"
