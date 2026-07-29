"""Tests for github_mcp.actions_config."""

from __future__ import annotations

import json
from base64 import b64decode

import httpx
import pytest
from nacl import encoding, public

from github_mcp import actions_config, core
from github_mcp.client import GitHubClient, GitHubError
from github_mcp.config import Config


def install_mock(monkeypatch, handler, *, token="test-token", read_only=False):
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
    )


async def test_list_repo_secrets_names_only(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/secrets"
        return httpx.Response(200, json={"total_count": 1, "secrets": [
            {"name": "PYPI_TOKEN", "created_at": "t", "updated_at": "t"}]})

    install_mock(monkeypatch, handler)
    result = await actions_config.list_repo_secrets("o", "r")
    assert result[0]["name"] == "PYPI_TOKEN"
    assert "value" not in result[0]


async def test_set_repo_secret_seals_value(monkeypatch):
    priv = public.PrivateKey.generate()
    pub_b64 = priv.public_key.encode(encoder=encoding.Base64Encoder).decode()
    captured = {}

    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/repos/o/r/actions/secrets/public-key":
            return httpx.Response(200, json={"key_id": "kid123", "key": pub_b64})
        if request.method == "PUT" and p == "/repos/o/r/actions/secrets/PYPI_TOKEN":
            captured.update(json.loads(request.content))
            return httpx.Response(201)
        raise AssertionError(f"unexpected {request.method} {p}")

    install_mock(monkeypatch, handler)
    result = await actions_config.set_repo_secret("o", "r", "PYPI_TOKEN", "s3cret")
    assert result == {"set": True, "secret_name": "PYPI_TOKEN"}
    assert captured["key_id"] == "kid123"
    # the uploaded value is a sealed box that decrypts back to the plaintext
    opened = public.SealedBox(priv).decrypt(b64decode(captured["encrypted_value"]))
    assert opened == b"s3cret"


async def test_set_repo_secret_blocked_in_read_only(monkeypatch):
    install_mock(monkeypatch, lambda r: httpx.Response(200), read_only=True)
    with pytest.raises(GitHubError) as exc:
        await actions_config.set_repo_secret("o", "r", "X", "y")
    assert exc.value.status_code == 403


async def test_list_repo_variables_includes_values(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/variables"
        return httpx.Response(200, json={"variables": [
            {"name": "REGION", "value": "us-east", "created_at": "t",
             "updated_at": "t"}]})

    install_mock(monkeypatch, handler)
    result = await actions_config.list_repo_variables("o", "r")
    assert result[0] == {"name": "REGION", "value": "us-east",
                         "created_at": "t", "updated_at": "t"}


async def test_set_repo_variable_updates_existing(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/repos/o/r/actions/variables/REGION"
        return httpx.Response(204)

    install_mock(monkeypatch, handler)
    result = await actions_config.set_repo_variable("o", "r", "REGION", "eu-west")
    assert result == {"set": True, "name": "REGION", "value": "eu-west"}


async def test_set_repo_variable_creates_when_missing(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "PATCH":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path == "/repos/o/r/actions/variables":
            return httpx.Response(201)
        raise AssertionError("unexpected")

    install_mock(monkeypatch, handler)
    result = await actions_config.set_repo_variable("o", "r", "NEWVAR", "1")
    assert result["set"] is True
    assert ("POST", "/repos/o/r/actions/variables") in calls


async def test_list_run_artifacts(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/runs/5/artifacts"
        return httpx.Response(200, json={"artifacts": [
            {"id": 3, "name": "dist", "size_in_bytes": 100, "expired": False,
             "created_at": "t", "archive_download_url": "https://x/zip"}]})

    install_mock(monkeypatch, handler)
    result = await actions_config.list_run_artifacts("o", "r", 5)
    assert result[0]["name"] == "dist"
    assert result[0]["archive_download_url"] == "https://x/zip"


async def test_download_artifact_returns_url(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/actions/artifacts/3"
        return httpx.Response(200, json={"id": 3, "name": "dist",
            "size_in_bytes": 100, "expired": False,
            "archive_download_url": "https://x/zip"})

    install_mock(monkeypatch, handler)
    result = await actions_config.download_artifact("o", "r", 3)
    assert result["archive_download_url"] == "https://x/zip"
