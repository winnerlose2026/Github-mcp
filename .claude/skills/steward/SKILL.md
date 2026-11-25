---
name: steward
description: House rules for PR Steward and /ship watches in this repository
user-invocable: false
disable-model-invocation: true
---

# PR Steward rules: Github-mcp

## Build and test (mirrors `ci.yml`)
- `pip install -e ".[dev]"`, then `ruff check .` and `pytest -q`.
- CI tests Python 3.10 through 3.13 and runs a wheel-install smoke test on Linux and Windows. Keep code compatible with 3.10.

## Don't
- Don't bump the version, edit `CHANGELOG.md` release headings, or create tags or releases. Publishing to PyPI runs from a published GitHub release and is the owner's call.
- Don't commit `.env` or tokens. Don't weaken, skip or delete tests or CI. Don't push to `main`.
