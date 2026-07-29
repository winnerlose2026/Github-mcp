"""One-shot refactor: dissolve server.py's tool bag into domain modules."""
from __future__ import annotations

import ast
import pathlib
import re
import sys

SRC = pathlib.Path("src/github_mcp")

TOOLS = {
    "account": ["get_authenticated_user"],
    "search": ["search_repositories", "search_issues", "search_code",
               "search_pull_requests", "search_commits", "search_users"],
    "repos": ["get_repository", "list_my_repositories", "get_repository_tree",
              "list_branches", "create_branch", "delete_branch",
              "create_repository", "fork_repository", "find_reusable_repositories"],
    "files": ["get_file_contents", "create_or_update_file", "delete_file"],
    "commits": ["list_commits", "get_commit", "compare_commits",
                "get_combined_status", "list_check_runs"],
    "issues": ["list_issues", "get_issue", "create_issue", "update_issue",
               "add_issue_comment", "list_issue_comments", "add_labels",
               "remove_label", "add_assignees", "list_labels", "create_label",
               "update_label", "delete_label"],
    "pulls": ["list_pull_requests", "get_pull_request", "get_pull_request_diff",
              "list_pull_request_files", "list_pull_request_reviews",
              "list_pull_request_review_comments", "create_pull_request",
              "update_pull_request", "merge_pull_request",
              "submit_pull_request_review", "add_pull_request_review_comment",
              "request_pull_request_reviewers"],
    "actions": ["list_workflow_runs", "list_workflow_run_jobs", "get_job_logs",
                "rerun_workflow_run", "trigger_workflow",
                "create_scheduled_workflow"],
    "releases": ["list_releases", "get_latest_release", "get_release_by_tag",
                 "create_release", "list_tags", "get_tag"],
    "alerts": ["list_secret_scanning_alerts", "list_code_scanning_alerts",
               "list_dependabot_alerts"],
    "gists": ["list_gists", "get_gist", "create_gist", "update_gist"],
    "notifications": ["list_notifications", "mark_notification_read"],
}
RELOCATE = {
    "extras": {"update_pull_request_branch": "pulls",
               "update_issue_comment": "issues", "delete_issue_comment": "issues",
               "delete_release_asset": "releases",
               "download_release_asset": "releases", "delete_gist": "gists",
               "mark_all_notifications_read": "notifications"},
    "repo_admin": {"add_repository_collaborator": "repos",
                   "remove_repository_collaborator": "repos",
                   "get_branch_protection": "repos",
                   "update_branch_protection": "repos", "merge_branch": "repos"},
    "repos": {"get_user": "account", "get_rate_limit": "account"},
}
DOC = {
    "account": "Account and quota tools: the token's own identity, other users, rate limits.",
    "search": "GitHub search. Every tool here takes raw qualifiers (e.g. `repo:o/n`, `is:open`).",
    "repos": "Repositories: metadata, branches, trees, collaborators, protection, creation.",
    "files": "File contents: read a file or directory, commit a change, delete a file.",
    "commits": "Commit history, diffs between refs, commit statuses, and check runs.",
    "issues": "Issues: read/write, comments, labels, assignees, milestones, locking.",
    "pulls": "Pull requests: listing, diffs, files, reviews, comments, and write actions.",
    "actions": "GitHub Actions: workflow definitions, runs, jobs, logs, dispatch, cancel.",
    "releases": "Releases and tags: read, create, edit, delete, and release assets.",
    "alerts": "Security alerts: Dependabot, code scanning, and secret scanning.",
    "gists": "Gists belonging to the authenticated user.",
    "notifications": "Notification inbox: list threads and mark them read.",
    "actions_config": "Actions configuration: secrets, variables, and run artifacts.",
    "deployments": "Deployment gates: environments awaiting approval, and approving them.",
}


def parse(path):
    """Split a module into (docstring, [(name, source)]) preserving order.

    Statement-based, not function-based: module-level constants travel with
    their module instead of being silently dropped.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    doc = ast.get_docstring(tree)
    items = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue                                    # module docstring
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue                                    # regenerated
        start = node.lineno
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            start = min([d.lineno for d in node.decorator_list] + [start])
        name = getattr(node, "name", None)
        if name is None:
            tgts = getattr(node, "targets", []) or [getattr(node, "target", None)]
            name = next((t.id for t in tgts if isinstance(t, ast.Name)), "?")
        items.append((name, "".join(lines[start - 1:node.end_lineno]).rstrip("\n")))
    return doc, items


def used(code: str) -> set[str]:
    t = ast.parse(code)
    return ({n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
            | {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)}
            | set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", code)))


def imports_for(code: str, defined: set[str]) -> str:
    names = used(code)
    std = ["from typing import Any"]
    if re.search(r"\bbase64\.", code):
        std.append("import base64")
    b64 = sorted({n for n in ("b64decode", "b64encode") if n in names})
    if b64:
        std.append("from base64 import " + ", ".join(b64))
    if re.search(r"\bre\.", code):
        std.append("import re")
    if "quote" in names:
        std.append("from urllib.parse import quote")
    out = ["from __future__ import annotations", ""] + sorted(std) + [""]
    local = []
    if "GitHubError" in names:
        local.append("from .client import GitHubError")
    core = [n for n in ("_clamp", "_session", "config", "mcp")
            if n in names and n not in defined]
    if core:
        local.append("from .core import " + ", ".join(sorted(core)))
    summ = sorted(n for n in names
                  if n.startswith("_summarize_") and n not in defined)
    if summ:
        local.append("from .summaries import " + ", ".join(summ))
    return "\n".join(out + local) + "\n"


def write_module(name, doc, items):
    body = "\n\n\n".join(src for _, src in items)
    defined = {n for n, _ in items}
    header = f'"""{doc}\n\n' if "\n" in doc or len(doc) > 60 else f'"""{doc}\n\n'
    text = (header
            + "Tools register on the shared FastMCP instance from :mod:`github_mcp.core`;\n"
              "the package ``__init__`` imports this module to register them.\n"
              '"""\n\n'
            + imports_for(body, defined) + "\n\n" + body + "\n")
    (SRC / f"{name}.py").write_text(text, encoding="utf-8")


def main() -> int:
    sdoc, sitems = parse(SRC / "server.py")
    lookup = dict(sitems)

    # core.py -----------------------------------------------------------------
    core_order = ["config", "INSTRUCTIONS", "mcp", "_require_token",
                  "_require_write", "_clamp", "_session"]
    (SRC / "core.py").write_text(
        '"""Shared foundation for every tool module.\n\n'
        "Holds the FastMCP instance, the resolved configuration, and the auth and\n"
        "session plumbing every tool runs through. Tool modules import from here;\n"
        "nothing here imports them, so there are no cycles.\n"
        '"""\n\nfrom __future__ import annotations\n\n'
        "from contextlib import asynccontextmanager\n\n"
        "from mcp.server.fastmcp import FastMCP\n\n"
        "from .client import GitHubClient, GitHubError\n"
        "from .config import Config\n\n\n"
        + "\n\n\n".join(lookup[n] for n in core_order) + "\n",
        encoding="utf-8")

    # summaries.py ------------------------------------------------------------
    summ = [(n, s) for n, s in sitems if n.startswith("_summarize_")]
    (SRC / "summaries.py").write_text(
        '"""Response shaping.\n\n'
        "Each helper trims a GitHub API payload to the fields worth showing a\n"
        "model and drops the rest. Pure functions: no I/O, no configuration.\n"
        '"""\n\nfrom __future__ import annotations\n\nfrom typing import Any\n\n\n'
        + "\n\n\n".join(s for _, s in summ) + "\n", encoding="utf-8")

    # harvest ----------------------------------------------------------------
    harvest: dict[str, list[tuple[str, str]]] = {m: [] for m in DOC}
    for module, names in TOOLS.items():
        harvest[module] += [(n, lookup[n]) for n in names]

    keep_existing: dict[str, list[tuple[str, str]]] = {}
    docs: dict[str, str] = {}
    for origin, mapping in RELOCATE.items():
        odoc, oitems = parse(SRC / f"{origin}.py")
        docs[origin] = odoc
        moved = {n for n in mapping}
        kept = [(n, s) for n, s in oitems if n not in moved]
        for n, s in oitems:
            if n in moved:
                harvest[mapping[n]].append((n, s))
        tools_left = [n for n, s in kept if "@mcp.tool()" in s]
        if tools_left:
            keep_existing[origin] = kept
        else:
            for n, s in kept:                 # constants follow their tools
                harvest[next(iter(mapping.values()))].insert(0, (n, s))
            (SRC / f"{origin}.py").unlink()

    # write every domain module ----------------------------------------------
    for module in DOC:
        items: list[tuple[str, str]] = []
        p = SRC / f"{module}.py"
        if module in keep_existing:
            items += keep_existing[module]
        elif p.exists():
            _, ex = parse(p)
            items += ex
        items += harvest[module]
        if not items:
            continue
        write_module(module, DOC[module], items)

    # server.py --------------------------------------------------------------
    (SRC / "server.py").write_text(
        '"""Console entry point.\n\n'
        "The tools live in the domain modules imported by the package\n"
        "``__init__``; this module only parses CLI arguments and starts the\n"
        "shared FastMCP instance::\n\n"
        "    python -m github_mcp            # stdio (Claude Desktop/Code)\n"
        "    python -m github_mcp --http     # streamable HTTP\n"
        '"""\n\nfrom __future__ import annotations\n\n'
        "# Importing the package registers every tool on the shared instance.\n"
        "import github_mcp  # noqa: F401\n\nfrom .core import mcp\n\n\n"
        + lookup["main"] + "\n\n\n"
        'if __name__ == "__main__":\n    main()\n', encoding="utf-8")

    # __init__ ---------------------------------------------------------------
    init = SRC / "__init__.py"
    version = re.search(r'__version__ = "([^"]+)"',
                        init.read_text(encoding="utf-8")).group(1)
    mods = sorted(p.stem for p in SRC.glob("*.py")
                  if p.stem not in {"__init__", "__main__", "client", "config",
                                    "core", "summaries", "server"})
    out = ['"""A Model Context Protocol (MCP) connector for GitHub.', "",
           "Exposes GitHub REST API operations as MCP tools so Claude (Desktop, Code,",
           "or any MCP client) can read and act on repositories, issues, pull requests,",
           "CI, releases, and security alerts.", '"""', "",
           "# `core` builds the shared FastMCP instance; importing each domain module",
           "# registers its @mcp.tool() functions on it. Import order is irrelevant:",
           "# every module takes the instance from `core`.",
           "from . import core as core  # noqa: F401"]
    out += [f"from . import {m} as {m}  # noqa: F401" for m in mods]
    out += ["from . import summaries as summaries  # noqa: F401", "",
            f'__version__ = "{version}"', "", "__all__ = [", '    "__version__",',
            '    "core",', '    "summaries",']
    out += [f'    "{m}",' for m in mods] + ["]"]
    init.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("domain modules:", ", ".join(mods))
    return 0


if __name__ == "__main__":
    sys.exit(main())
