"""Retarget the test suite at the new module layout.

`_session` moved to `core`, so `install_mock` must patch `core` rather than
`server`; and each tool now lives in a domain module, so `server.foo()` calls
are rewritten to `<module>.foo()`. test_server.py is split the same way its
tools were.
"""
from __future__ import annotations

import ast
import pathlib
import re

SRC = pathlib.Path("src/github_mcp")
TESTS = pathlib.Path("tests")

INSTALL_MOCK = '''def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
    """Point the shared session at a mocked GitHub API.

    Tools call `core._session`, which reads `core.config` and
    `core.GitHubClient`, so those are what we patch.
    """
    cfg = Config(
        token=token,
        api_url="https://api.github.com",
        read_only=read_only,
        timeout=5.0,
        user_agent="test-agent",
    )
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(core, "config", cfg)
    monkeypatch.setattr(
        core, "GitHubClient", lambda c: GitHubClient(c, transport=transport)
    )'''


def extra_imports() -> dict[str, str]:
    """Map bound name -> import line, for imports we don't regenerate.

    Keeps third-party imports (e.g. `nacl`) that individual tests rely on.
    """
    known = {"httpx", "json", "pytest", "annotations"}
    out: dict[str, str] = {}
    for p in TESTS.glob("test_*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in tree.body:
            if not isinstance(n, ast.Import | ast.ImportFrom):
                continue
            mod = getattr(n, "module", "") or ""
            if mod.startswith("github_mcp"):
                continue
            for a in n.names:
                bound = a.asname or a.name.split(".")[0]
                if bound in known:
                    continue
                out[bound] = (f"from {mod} import {a.name}"
                              if isinstance(n, ast.ImportFrom)
                              else f"import {a.name}")
    return out


def tool_owners() -> dict[str, str]:
    owners = {}
    for p in SRC.glob("*.py"):
        if p.stem in {"__init__", "__main__", "client", "config", "core",
                      "summaries", "server"}:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in tree.body:
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                if any("tool" in ast.dump(d) for d in n.decorator_list):
                    owners[n.name] = p.stem
    return owners


def body_items(path):
    """Top-level test functions (name, source), skipping imports/install_mock."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    out = []
    for n in tree.body:
        if isinstance(n, ast.Import | ast.ImportFrom):
            continue
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            continue
        if getattr(n, "name", "") == "install_mock":
            continue
        start = min([d.lineno for d in n.decorator_list] + [n.lineno]) \
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) else n.lineno
        out.append((getattr(n, "name", "?"),
                    "".join(lines[start - 1:n.end_lineno]).rstrip("\n")))
    return out


def retarget(code: str, owners: dict[str, str]) -> tuple[str, set[str]]:
    """Rewrite server.X / <mod>.X calls to the owning module. Returns modules used."""
    mods: set[str] = set()

    # any `<something>.tool_name(` where tool_name is a known tool
    def sub(m):
        mod, name = m.group(1), m.group(2)
        if name in owners:
            mods.add(owners[name])
            return f"{owners[name]}.{name}("
        return m.group(0)

    code = re.sub(r"\b([a-z_]+)\.([a-z_]+)\(", sub, code)
    return code, mods


def emit(path: pathlib.Path, doc: str, items, owners, extras):
    bodies, mods = [], set()
    for _, src in items:
        new, used = retarget(src, owners)
        bodies.append(new)
        mods |= used
    body = "\n\n\n".join(bodies)
    imports = ["from __future__ import annotations", ""]
    if re.search(r"\bjson\.", body):
        imports.append("import json")
    imports.append("import httpx")
    if "pytest." in body:
        imports.append("import pytest")
    for name, line in sorted(extras.items()):
        if re.search(rf"\b{re.escape(name)}\b", body):
            imports.append(line)
    imports.append("")
    need = sorted(mods | {"core"})
    imports.append("from github_mcp import " + ", ".join(need))
    cli = ["GitHubClient"] + (["GitHubError"] if "GitHubError" in body else [])
    imports.append("from github_mcp.client import " + ", ".join(cli))
    imports.append("from github_mcp.config import Config")
    path.write_text(f'"""{doc}"""\n\n' + "\n".join(imports) + "\n\n\n"
                    + INSTALL_MOCK + "\n\n\n" + body + "\n", encoding="utf-8")


def main() -> int:
    owners = tool_owners()
    extras = extra_imports()
    # 1. route test_server.py's functions to the module owning the tools they call
    server_tests = body_items(TESTS / "test_server.py")
    routed: dict[str, list] = {}
    for name, src in server_tests:
        _, mods = retarget(src, owners)
        target = sorted(mods)[0] if mods else "core"
        routed.setdefault(target, []).append((name, src))
    (TESTS / "test_server.py").unlink()

    # 2. fold in the existing per-module test files, then emit
    gone = {"test_extras.py", "test_repo_admin.py"}
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name in {"test_client.py", "test_config.py", "test_registry.py"}:
            continue
        stem = p.stem.replace("test_", "")
        items = body_items(p)
        if p.name in gone:                      # dissolved modules' tests re-home
            for name, src in items:
                _, mods = retarget(src, owners)
                routed.setdefault(sorted(mods)[0] if mods else "core", []).append(
                    (name, src))
            p.unlink()
            continue
        routed.setdefault(stem, [])
        routed[stem] = items + routed[stem]

    for module, items in sorted(routed.items()):
        if not items:
            continue
        emit(TESTS / f"test_{module}.py",
             f"Tests for github_mcp.{module}.", items, owners, extras)
    print("test modules:", ", ".join(sorted(f"test_{m}" for m in routed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
