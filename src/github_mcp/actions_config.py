"""GitHub Actions configuration: secrets, variables, and run artifacts.

Complements the workflow tools in :mod:`github_mcp.server` and
:mod:`github_mcp.actions`. Secrets are write-encrypted with the repository's
public key (libsodium sealed box, via PyNaCl) so plaintext never leaves this
process; secret values are never read back. Variables are plaintext config.
Write tools are disabled in read-only mode. The package ``__init__`` imports
this module to register them.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from typing import Any

from .client import GitHubError
from .server import _clamp, _session, mcp


@mcp.tool()
async def list_repo_secrets(
    owner: str, repo: str, limit: int = 30
) -> list[dict[str, Any]]:
    """List the names of a repository's Actions secrets (values are never exposed).

    Returns each secret's name and created/updated timestamps. GitHub never
    returns secret values, so neither does this. Returns up to `limit` (max 100).
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        data = await gh.get(
            f"/repos/{owner}/{repo}/actions/secrets", params={"per_page": limit}
        )
    return [
        {
            "name": s.get("name"),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        }
        for s in data.get("secrets", [])
    ]


@mcp.tool()
async def set_repo_secret(
    owner: str, repo: str, secret_name: str, value: str
) -> dict[str, Any]:
    """Create or update a repository Actions secret (a gated write).

    The value is encrypted client-side with the repo's public key (a libsodium
    sealed box) before upload, so the plaintext is only ever held in memory.
    Creates the secret if absent, updates it otherwise. Requires a token with
    write access to Actions secrets, and the `PyNaCl` package.
    """
    try:
        from nacl import public
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise GitHubError(
            500,
            "PUT",
            f"/repos/{owner}/{repo}/actions/secrets/{secret_name}",
            "PyNaCl is required to encrypt secrets (pip install pynacl).",
        ) from exc
    async with _session(write=True) as gh:
        key = await gh.get(f"/repos/{owner}/{repo}/actions/secrets/public-key")
        sealed = public.SealedBox(public.PublicKey(b64decode(key["key"]))).encrypt(
            value.encode("utf-8")
        )
        await gh.put(
            f"/repos/{owner}/{repo}/actions/secrets/{secret_name}",
            json={
                "encrypted_value": b64encode(sealed).decode("utf-8"),
                "key_id": key["key_id"],
            },
        )
    return {"set": True, "secret_name": secret_name}


@mcp.tool()
async def delete_repo_secret(
    owner: str, repo: str, secret_name: str
) -> dict[str, Any]:
    """Delete a repository Actions secret (a gated write)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/actions/secrets/{secret_name}")
    return {"deleted": True, "secret_name": secret_name}


@mcp.tool()
async def list_repo_variables(
    owner: str, repo: str, limit: int = 30
) -> list[dict[str, Any]]:
    """List a repository's Actions variables (name + value; these are not secret).

    Returns up to `limit` (max 100) variables with their values and timestamps.
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        data = await gh.get(
            f"/repos/{owner}/{repo}/actions/variables", params={"per_page": limit}
        )
    return [
        {
            "name": v.get("name"),
            "value": v.get("value"),
            "created_at": v.get("created_at"),
            "updated_at": v.get("updated_at"),
        }
        for v in data.get("variables", [])
    ]


@mcp.tool()
async def set_repo_variable(
    owner: str, repo: str, name: str, value: str
) -> dict[str, Any]:
    """Create or update a repository Actions variable (a gated write).

    Updates the variable if it exists, otherwise creates it. Variables are
    plaintext config (use `set_repo_secret` for sensitive values).
    """
    async with _session(write=True) as gh:
        try:
            await gh.patch(
                f"/repos/{owner}/{repo}/actions/variables/{name}",
                json={"name": name, "value": value},
            )
        except GitHubError as exc:
            if exc.status_code == 404:
                await gh.post(
                    f"/repos/{owner}/{repo}/actions/variables",
                    json={"name": name, "value": value},
                )
            else:
                raise
    return {"set": True, "name": name, "value": value}


@mcp.tool()
async def delete_repo_variable(owner: str, repo: str, name: str) -> dict[str, Any]:
    """Delete a repository Actions variable (a gated write)."""
    async with _session(write=True) as gh:
        await gh.delete(f"/repos/{owner}/{repo}/actions/variables/{name}")
    return {"deleted": True, "name": name}


@mcp.tool()
async def list_run_artifacts(
    owner: str, repo: str, run_id: int, limit: int = 30
) -> list[dict[str, Any]]:
    """List the artifacts produced by a workflow run.

    Returns each artifact's id, name, size, expiry, and `archive_download_url`
    (a short-lived API URL for the zip). Returns up to `limit` (max 100).
    """
    limit = _clamp(limit, 100)
    async with _session() as gh:
        data = await gh.get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
            params={"per_page": limit},
        )
    return [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "size_in_bytes": a.get("size_in_bytes"),
            "expired": a.get("expired"),
            "created_at": a.get("created_at"),
            "archive_download_url": a.get("archive_download_url"),
        }
        for a in data.get("artifacts", [])
    ]


@mcp.tool()
async def download_artifact(
    owner: str, repo: str, artifact_id: int
) -> dict[str, Any]:
    """Get a download link for a single run artifact.

    Returns the artifact's metadata and `archive_download_url` (a short-lived
    URL for the zip). The binary itself isn't streamed back over MCP — use the
    URL to fetch it.
    """
    async with _session() as gh:
        a = await gh.get(f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}")
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "size_in_bytes": a.get("size_in_bytes"),
        "expired": a.get("expired"),
        "archive_download_url": a.get("archive_download_url"),
    }
