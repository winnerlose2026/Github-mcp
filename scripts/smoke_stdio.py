"""Launch the connector over stdio and assert it completes an MCP handshake.

Unit tests import the package in-process, which does *not* prove a client can
actually start the server: a broken dependency resolution (e.g. the mcp 2.0
release that removed ``mcp.server.fastmcp``) only shows up at launch. This
script speaks real JSON-RPC to ``python -m github_mcp`` the way Claude does,
then checks the server initializes and lists a plausible number of tools.

Usage: python scripts/smoke_stdio.py [--min-tools N]
Exits non-zero with a diagnostic on any failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

REQUESTS = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-tools", type=int, default=100)
    args = parser.parse_args()

    payload = "".join(json.dumps(r) + "\n" for r in REQUESTS)
    # Inherit the real environment (Windows needs SYSTEMROOT/PATH for the
    # interpreter to start at all) and only inject the token. A dummy value is
    # enough: no tool is called, and startup must not depend on it being valid.
    env = dict(os.environ, GITHUB_TOKEN="smoke-dummy")
    proc = subprocess.run(
        [sys.executable, "-m", "github_mcp"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    initialized = False
    tool_count = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == 1 and "result" in msg:
            initialized = True
        if msg.get("id") == 2 and "result" in msg:
            tool_count = len(msg["result"].get("tools", []))

    if not initialized:
        print("SMOKE FAIL: server never completed `initialize`.", file=sys.stderr)
        print(f"exit code: {proc.returncode}", file=sys.stderr)
        print("--- stderr ---", file=sys.stderr)
        print(proc.stderr[-3000:], file=sys.stderr)
        return 1

    if tool_count is None:
        print("SMOKE FAIL: server did not answer `tools/list`.", file=sys.stderr)
        print(proc.stderr[-3000:], file=sys.stderr)
        return 1

    if tool_count < args.min_tools:
        print(
            f"SMOKE FAIL: only {tool_count} tools registered, "
            f"expected >= {args.min_tools}. Did a module fail to import?",
            file=sys.stderr,
        )
        return 1

    print(f"SMOKE OK: server initialized and registered {tool_count} tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
