"""Launch the connector over stdio and assert it completes an MCP handshake.

Unit tests import the package in-process, which does *not* prove a client can
actually start the server: a broken dependency resolution (e.g. the mcp 2.0
release that removed ``mcp.server.fastmcp``) only shows up at launch. This
script speaks real JSON-RPC to ``python -m github_mcp`` the way Claude does,
then checks the server initializes and lists a plausible number of tools.

Responses are read incrementally while stdin stays open. Feeding the process a
fixed string and letting stdin close (``subprocess.run(input=...)``) races the
server's shutdown-on-EOF against its reply, which passes on slow platforms and
fails on fast ones.

Usage: python scripts/smoke_stdio.py [--min-tools N] [--timeout SECONDS]
Exits non-zero with a diagnostic on any failure.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

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


def _drain(stream, sink: queue.Queue) -> None:
    """Pump a pipe into a queue, line by line, until it closes."""
    for line in iter(stream.readline, ""):
        sink.put(line)
    sink.put(None)  # sentinel: stream closed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-tools", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    # Inherit the real environment (Windows needs SYSTEMROOT/PATH for the
    # interpreter to start at all) and only inject the token. A dummy value is
    # enough: no tool is called, and startup must not depend on it being valid.
    env = dict(os.environ, GITHUB_TOKEN="smoke-dummy")
    proc = subprocess.Popen(
        [sys.executable, "-m", "github_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    out: queue.Queue = queue.Queue()
    threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True).start()
    stderr_chunks: list[str] = []
    threading.Thread(
        target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True
    ).start()

    def fail(reason: str) -> int:
        proc.kill()
        proc.wait(timeout=10)
        print(f"SMOKE FAIL: {reason}", file=sys.stderr)
        print(f"exit code: {proc.returncode}", file=sys.stderr)
        print("--- server stderr ---", file=sys.stderr)
        print(("".join(stderr_chunks))[-3000:], file=sys.stderr)
        return 1

    try:
        for request in REQUESTS:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return fail("server exited before the requests could be sent.")

    initialized = False
    tool_count: int | None = None
    deadline = time.monotonic() + args.timeout

    # Keep stdin open so the server has no reason to shut down mid-reply.
    while tool_count is None and time.monotonic() < deadline:
        try:
            line = out.get(timeout=1.0)
        except queue.Empty:
            if proc.poll() is not None:
                return fail("server exited before answering `tools/list`.")
            continue
        if line is None:
            return fail("server closed stdout before answering `tools/list`.")
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
        return fail("server never completed `initialize`.")
    if tool_count is None:
        return fail(f"no `tools/list` reply within {args.timeout:g}s.")
    if tool_count < args.min_tools:
        return fail(
            f"only {tool_count} tools registered, expected >= {args.min_tools}. "
            "Did a module fail to import?"
        )

    proc.stdin.close()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    print(f"SMOKE OK: server initialized and registered {tool_count} tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
