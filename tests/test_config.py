"""Tests for environment-driven configuration."""


from github_mcp.config import Config


def test_defaults(monkeypatch):
    for var in (
        "GITHUB_TOKEN",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "GH_TOKEN",
        "GITHUB_API_URL",
        "GITHUB_MCP_READ_ONLY",
        "GITHUB_MCP_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.from_env()
    assert cfg.token is None
    assert cfg.api_url == "https://api.github.com"
    assert cfg.read_only is False
    assert cfg.timeout == 30.0


def test_token_priority(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "primary")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "secondary")
    assert Config.from_env().token == "primary"

    monkeypatch.delenv("GITHUB_TOKEN")
    assert Config.from_env().token == "secondary"


def test_api_url_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", "https://ghe.example.com/api/v3/")
    assert Config.from_env().api_url == "https://ghe.example.com/api/v3"


def test_read_only_parsing(monkeypatch):
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("GITHUB_MCP_READ_ONLY", truthy)
        assert Config.from_env().read_only is True
    for falsy in ("0", "false", "no", ""):
        monkeypatch.setenv("GITHUB_MCP_READ_ONLY", falsy)
        assert Config.from_env().read_only is False


def test_invalid_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("GITHUB_MCP_TIMEOUT", "not-a-number")
    assert Config.from_env().timeout == 30.0
