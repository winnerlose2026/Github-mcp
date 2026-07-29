"""Apply the 0.18.0 changes: retry/backoff, tool-group scoping, pagination."""
from __future__ import annotations

import ast
import pathlib
import re
import sys

SRC = pathlib.Path("src/github_mcp")
NOTE = ("Paginated: returns at most `limit` items from page `page` (1-based). "
        "If you get exactly `limit` items there are probably more; request "
        "`page=2`, and so on.")


# ---------------------------------------------------------------- pagination
def paginate() -> int:
    touched = 0
    for path in sorted(SRC.glob("*.py")):
        if path.stem in {"__init__", "__main__", "client", "config", "core",
                         "summaries", "server"}:
            continue
        src = path.read_text(encoding="utf-8")
        names = []
        for node in ast.parse(src).body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not any("tool" in ast.dump(d) for d in node.decorator_list):
                continue
            seg = ast.get_source_segment(src, node) or ""
            if '"per_page"' not in seg or '"page"' in seg:
                continue
            args = [a.arg for a in node.args.args]
            if "page" in args or "limit" not in args:
                continue
            names.append(node.name)
        for name in names:
            src = _add_page(src, name)
            touched += 1
        if names:
            path.write_text(src, encoding="utf-8")
            print(f"  {path.name}: {', '.join(names)}")
    return touched


def _add_page(src: str, name: str) -> str:
    node = next(n for n in ast.parse(src).body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                and n.name == name)
    seg = ast.get_source_segment(src, node)
    new = seg

    # signature: append `page: int = 1` as the last defaulted parameter
    open_at = new.index("(", new.index(f"def {name}"))
    depth, close_at = 0, -1
    for i in range(open_at, len(new)):
        if new[i] == "(":
            depth += 1
        elif new[i] == ")":
            depth -= 1
            if depth == 0:
                close_at = i
                break
    params = new[open_at + 1:close_at]
    if "\n" in params:                                   # one param per line
        indent = re.match(r"\n(\s*)", params).group(1)
        tail = re.search(r"\n\s*$", params)
        body = params[:tail.start()] if tail else params
        addition = f"{body.rstrip().rstrip(',')},\n{indent}page: int = 1,"
        addition += tail.group(0) if tail else ""
    else:
        addition = f"{params.rstrip().rstrip(',')}, page: int = 1"
    new = new[:open_at + 1] + addition + new[close_at:]

    # query string
    new = new.replace('"per_page": limit', '"per_page": limit, "page": page')

    # docstring: append the note as its own paragraph, at the docstring's indent
    first = new.index('"""')
    closing = new.index('"""', first + 3)
    line_start = new.rfind("\n", 0, closing) + 1
    pad = new[line_start:closing]
    pad = pad if not pad.strip() else "    "
    body_end = len(new[:closing].rstrip())               # last real character
    wrapped, line = [], ""
    for word in NOTE.split():
        candidate = f"{line} {word}".strip()
        if len(pad) + len(candidate) > 79:
            wrapped.append(pad + line)
            line = word
        else:
            line = candidate
    wrapped.append(pad + line)
    return src.replace(seg, new[:body_end] + "\n\n" + "\n".join(wrapped)
                       + new[body_end:], 1)


# ------------------------------------------------------------------ scoping
def scoping() -> None:
    p = SRC / "config.py"
    s = p.read_text(encoding="utf-8")
    old_cls = '''@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    token: str | None
    api_url: str
    read_only: bool
    timeout: float
    user_agent: str
'''
    new_cls = '''# Domain modules selectable with GITHUB_MCP_TOOLS. `core` and `summaries` are
# infrastructure and always loaded.
TOOL_GROUPS = (
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
)


def _read_tool_groups() -> frozenset[str] | None:
    """Parse GITHUB_MCP_TOOLS into module names, or None meaning "all".

    Loading only the groups you need trims the tool list every client session
    carries. An unknown name is a hard error rather than a silent no-op, because
    quietly exposing nothing looks like a broken connector.
    """
    raw = os.environ.get("GITHUB_MCP_TOOLS", "").strip()
    if not raw:
        return None
    wanted = {part.strip() for part in raw.replace(",", " ").split() if part.strip()}
    unknown = sorted(wanted - set(TOOL_GROUPS))
    if unknown:
        raise ValueError(
            f"GITHUB_MCP_TOOLS names unknown tool group(s): {', '.join(unknown)}. "
            f"Valid groups: {', '.join(TOOL_GROUPS)}."
        )
    return frozenset(wanted)


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    token: str | None
    api_url: str
    read_only: bool
    timeout: float
    user_agent: str
    # Defaulted so callers (and tests) predating these can omit them.
    max_retries: int = 3
    tool_groups: frozenset[str] | None = None
'''
    assert s.count(old_cls) == 1, "config class anchor"
    s = s.replace(old_cls, new_cls, 1)
    old_ret = '''        return cls(
            token=_read_token(),
            api_url=api_url,
            read_only=_read_bool("GITHUB_MCP_READ_ONLY", default=False),
            timeout=timeout,
            user_agent=os.environ.get("GITHUB_MCP_USER_AGENT", "github-mcp-connector"),
        )'''
    new_ret = '''        retries_raw = os.environ.get("GITHUB_MCP_MAX_RETRIES", "3")
        try:
            max_retries = max(0, int(retries_raw))
        except ValueError:
            max_retries = 3
        return cls(
            token=_read_token(),
            api_url=api_url,
            read_only=_read_bool("GITHUB_MCP_READ_ONLY", default=False),
            timeout=timeout,
            user_agent=os.environ.get("GITHUB_MCP_USER_AGENT", "github-mcp-connector"),
            max_retries=max_retries,
            tool_groups=_read_tool_groups(),
        )'''
    assert s.count(old_ret) == 1, "config from_env anchor"
    p.write_text(s.replace(old_ret, new_ret, 1), encoding="utf-8")

    init = SRC / "__init__.py"
    version = re.search(r'__version__ = "([^"]+)"',
                        init.read_text(encoding="utf-8")).group(1)
    init.write_text('''"""A Model Context Protocol (MCP) connector for GitHub.

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

__version__ = "''' + version + '''"

__all__ = ["__version__", "core", "summaries", *sorted(_selected)]
''', encoding="utf-8")


# -------------------------------------------------------------------- retry
def retry() -> None:
    p = SRC / "client.py"
    s = p.read_text(encoding="utf-8")
    s = s.replace(
"""The wrapper is intentionally small: it handles authentication, the standard
headers GitHub expects, error translation, and a tiny bit of pagination. Each
MCP tool in :mod:`github_mcp.server` builds on top of these primitives.""",
"""The wrapper is intentionally small: it handles authentication, the standard
headers GitHub expects, error translation, and retrying the failures worth
retrying. The tool modules (see the package ``__init__``) build on these
primitives; page selection is the tools' own `page` argument.""")
    s = s.replace("from __future__ import annotations\n\nfrom typing import Any",
                  "from __future__ import annotations\n\nimport asyncio\n"
                  "import random\nimport time\nfrom typing import Any")
    s = s.replace('''GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_API_VERSION = "2022-11-28"''',
'''GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_API_VERSION = "2022-11-28"

# Statuses worth another attempt. A 429, or a 403 that is really a rate limit,
# means GitHub rejected the request without processing it, so retrying is safe
# for any method. A 5xx is ambiguous for writes -- the change may already have
# applied -- so those are retried for reads only (see `_should_retry`).
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_BACKOFF_SECONDS = 60.0


def _is_rate_limited(response: httpx.Response) -> bool:
    """True when GitHub is throttling us rather than refusing the request."""
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    if response.headers.get("x-ratelimit-remaining") == "0":
        return True
    body = response.text[:500].lower()
    return "rate limit" in body or "abuse detection" in body


def _should_retry(method: str, response: httpx.Response) -> bool:
    if _is_rate_limited(response):
        return True
    if response.status_code in _RETRY_STATUSES:
        # Reads only: replaying a POST/PATCH/DELETE that may have been applied
        # could double-create or double-delete.
        return method in ("GET", "HEAD")
    return False


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Wait time, preferring GitHub's own guidance over guesswork."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    if response.headers.get("x-ratelimit-remaining") == "0":
        reset = response.headers.get("x-ratelimit-reset")
        if reset:
            try:
                wait = float(reset) - time.time()
            except ValueError:
                wait = 0.0
            if wait > 0:
                return min(wait, _MAX_BACKOFF_SECONDS)
    # Exponential with jitter, so retries from concurrent tools don't align.
    return min(2.0**attempt + random.uniform(0, 0.5), _MAX_BACKOFF_SECONDS)''')
    old = '''        try:
            response = await self._client.request(
                method,
                path,
                params=clean_params,
                json=json,
                content=content,
                headers=headers or None,
            )
        except httpx.HTTPError as exc:  # network/timeout errors
            raise GitHubError(0, method, path, f"request error: {exc}") from exc

        if response.status_code >= 400:'''
    new = '''        attempts = self._config.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=clean_params,
                    json=json,
                    content=content,
                    headers=headers or None,
                )
            except httpx.HTTPError as exc:  # network/timeout errors
                if method in ("GET", "HEAD") and attempt < attempts - 1:
                    await asyncio.sleep(min(2.0**attempt, _MAX_BACKOFF_SECONDS))
                    continue
                raise GitHubError(0, method, path, f"request error: {exc}") from exc
            if attempt < attempts - 1 and _should_retry(method, response):
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            break

        if response.status_code >= 400:'''
    assert s.count(old) == 1, "client send anchor"
    p.write_text(s.replace(old, new, 1), encoding="utf-8")


# --------------------------------------------------------------------- docs
def docs() -> None:
    """Document the new env vars and record the change."""
    p = pathlib.Path("README.md")
    s = p.read_text(encoding="utf-8")
    old = "| `GITHUB_MCP_TIMEOUT` | no | `30` | Per-request timeout in seconds. |\n"
    assert s.count(old) == 1, "README config table anchor"
    s = s.replace(old, old
        + "| `GITHUB_MCP_MAX_RETRIES` | no | `3` | Retries for throttled requests "
          "(429 / rate-limited 403) and, for reads only, transient 5xx. Set `0` to "
          "disable. |\n"
        + "| `GITHUB_MCP_TOOLS` | no | *(all)* | Comma- or space-separated tool "
          "groups to load, e.g. `issues,pulls,repos`. Loading fewer groups shrinks "
          "the tool list each client session carries. Valid groups: `account`, "
          "`actions`, `actions_config`, `alerts`, `commits`, `deployments`, `files`, "
          "`gists`, `issues`, `notifications`, `pulls`, `releases`, `repos`, "
          "`search`. |\n", 1)
    oldf = "- \U0001F512 **Read-only mode** — flip one env var to disable every write tool\n"
    assert s.count(oldf) == 1, "README features anchor"
    s = s.replace(oldf,
        "- \U0001F4C4 **Pagination** — every list tool takes `page`, so you can read "
        "past the first 100 items\n"
        "- ♻️ **Resilient** — honours `Retry-After` and rate-limit headers; "
        "retries transient failures (never replaying a write)\n"
        "- \U0001F3AF **Scopable** — `GITHUB_MCP_TOOLS` loads only the tool groups "
        "you need\n"
        + oldf, 1)
    p.write_text(s, encoding="utf-8")

    p = pathlib.Path(".env.example")
    s = p.read_text(encoding="utf-8")
    old = ("# Optional: HTTP request timeout in seconds. Default: 30\n"
           "GITHUB_MCP_TIMEOUT=30\n")
    assert s.count(old) == 1, ".env.example anchor"
    p.write_text(s.replace(old, old + """
# Optional: how many times to retry a request GitHub rejected without running
# it (429, or a 403 that is really a rate limit) and, for reads only, transient
# 5xx responses. Writes are never replayed after an ambiguous 5xx. Default: 3
GITHUB_MCP_MAX_RETRIES=3

# Optional: load only some tool groups, comma- or space-separated. Fewer groups
# means a smaller tool list for every client session. Default: all groups.
# Valid: account, actions, actions_config, alerts, commits, deployments, files,
#        gists, issues, notifications, pulls, releases, repos, search
# Example: GITHUB_MCP_TOOLS=issues,pulls,repos
GITHUB_MCP_TOOLS=
""", 1), encoding="utf-8")

    p = pathlib.Path("CHANGELOG.md")
    s = p.read_text(encoding="utf-8")
    anchor = "## [0.17.0] — 2026-07-29"
    assert s.count(anchor) == 1, "CHANGELOG anchor"
    entry = """## [0.18.0] — 2026-07-29

### Fixed
- **List tools could only ever return the first 100 items.** Every paginated tool
  sent `per_page` but no `page`, so a repository with 300 open issues silently
  reported 100 of them — with nothing to indicate the answer was partial. All 34
  paginated tools now take `page` (1-based, default 1), and each docstring says
  how to tell there is more: getting exactly `limit` items means you should ask
  for the next page.
- Corrected two stale claims in `client.py`'s docstring: it advertised
  "a tiny bit of pagination" (there was none) and pointed at
  `github_mcp.server`, which 0.17.0 emptied.

### Added
- **Retry and backoff.** `Retry-After` and `x-ratelimit-reset` are honoured, with
  exponential backoff plus jitter otherwise, capped at 60s. Throttled requests
  (429, or a 403 that is really a rate limit) are retried for any method, since
  GitHub rejected them without running them. Transient 5xx responses are retried
  **for reads only** — replaying a `POST`/`PATCH`/`DELETE` that may already have
  applied could double-create or double-delete. Tunable with
  `GITHUB_MCP_MAX_RETRIES` (default 3, `0` disables).
- **`GITHUB_MCP_TOOLS`** loads only the tool groups you name, e.g.
  `issues,pulls,repos` — 33 tools instead of 122. Every session otherwise pays
  the context cost of the full surface. An unknown group name is a hard error
  rather than a silent no-op, because quietly exposing nothing looks like a
  broken connector.

Tool count is unchanged at 122; the 34 paginated tools gain an optional `page`
argument and nothing else changes about their signatures.

"""
    p.write_text(s.replace(anchor, entry + anchor, 1), encoding="utf-8")


if __name__ == "__main__":
    retry()
    scoping()
    docs()
    print("paginated tools:")
    print("total:", paginate())
    sys.exit(0)
