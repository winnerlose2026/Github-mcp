"""A thin async wrapper around the GitHub REST API.

The wrapper is intentionally small: it handles authentication, the standard
headers GitHub expects, error translation, and retrying the failures worth
retrying. The tool modules (see the package ``__init__``) build on these
primitives; page selection is the tools' own `page` argument.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from .config import Config

GITHUB_ACCEPT = "application/vnd.github+json"
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
    return min(2.0**attempt + random.uniform(0, 0.5), _MAX_BACKOFF_SECONDS)


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

    async def __aenter__(self) -> GitHubClient:
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
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type
        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )
        attempts = self._config.max_retries + 1
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

    async def put(self, path: str, *, json: dict[str, Any]) -> Any:
        response = await self._request("PUT", path, json=json)
        if not response.content:
            return None
        return response.json()

    async def patch(self, path: str, *, json: dict[str, Any]) -> Any:
        response = await self._request("PATCH", path, json=json)
        if not response.content:
            return None
        return response.json()

    async def delete(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        # GitHub returns 204 No Content for some deletes, but a body for others
        # (e.g. removing an issue label returns the remaining labels). A few
        # deletes (e.g. deleting file contents) also require a JSON body.
        response = await self._request("DELETE", path, json=json)
        if not response.content:
            return None
        return response.json()

    async def upload(
        self,
        url: str,
        *,
        data: bytes,
        content_type: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        # Release-asset uploads go to a different host (uploads.github.com) with
        # a raw binary body rather than JSON; `url` is the absolute upload URL.
        response = await self._request(
            "POST", url, params=params, content=data, content_type=content_type
        )
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
