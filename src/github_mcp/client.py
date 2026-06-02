"""A thin async wrapper around the GitHub REST API.

The wrapper is intentionally small: it handles authentication, the standard
headers GitHub expects, error translation, and a tiny bit of pagination. Each
MCP tool in :mod:`github_mcp.server` builds on top of these primitives.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config

GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns an error response.

    The message is formatted to be useful when surfaced back to an LLM: it
    includes the HTTP status, the requested method/path, and GitHub's own
    error message when one is available.
    """

    def __init__(self, status_code: int, method: str, url: str, detail: str) -> None:
        self.status_code = status_code
        self.method = method
        self.url = url
        self.detail = detail
        super().__init__(f"GitHub API {method} {url} failed ({status_code}): {detail}")


class GitHubClient:
    """Minimal async GitHub REST client.

    Use as an async context manager so the underlying connection pool is
    closed cleanly::

        async with GitHubClient(config) as gh:
            user = await gh.get("/user")
    """

    def __init__(
        self, config: Config, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._config = config
        headers = {
            "Accept": GITHUB_ACCEPT,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": config.user_agent,
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        # `transport` is an injection seam used by tests to mock the API; in
        # normal operation it is None and httpx uses its default transport.
        self._client = httpx.AsyncClient(
            base_url=config.api_url,
            headers=headers,
            timeout=config.timeout,
            follow_redirects=True,
            transport=transport,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- core request helpers -------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str | None = None,
    ) -> httpx.Response:
        headers = {"Accept": accept} if accept else None
        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )
        try:
            response = await self._client.request(
                method, path, params=clean_params, json=json, headers=headers
            )
        except httpx.HTTPError as exc:  # network/timeout errors
            raise GitHubError(0, method, path, f"request error: {exc}") from exc

        if response.status_code >= 400:
            raise GitHubError(
                response.status_code,
                method,
                str(response.request.url),
                _extract_error_detail(response),
            )
        return response

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        response = await self._request("GET", path, params=params)
        if not response.content:
            return None
        return response.json()

    async def get_raw(
        self, path: str, *, params: dict[str, Any] | None = None, accept: str
    ) -> str:
        response = await self._request("GET", path, params=params, accept=accept)
        return response.text

    async def post(self, path: str, *, json: dict[str, Any]) -> Any:
        response = await self._request("POST", path, json=json)
        if not response.content:
            return None
        return response.json()


def _extract_error_detail(response: httpx.Response) -> str:
    """Pull the most useful human-readable error message out of a response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500] or response.reason_phrase
    if isinstance(payload, dict):
        message = payload.get("message", "")
        errors = payload.get("errors")
        if errors:
            return f"{message}: {errors}"
        return message or str(payload)
    return str(payload)
