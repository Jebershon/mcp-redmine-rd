"""Tests for single-user local (stdio / API-key) wiring."""

from __future__ import annotations

import importlib
import os
import sys

import pytest

# Env vars server.py reads at import time.
_MODE_VARS = ("REDMINE_URL", "REDMINE_API_KEY", "REDMINE_CLIENT_ID", "REDMINE_CLIENT_SECRET")


def _reimport_server(env: dict[str, str]):
    """(Re)import server.py with exactly the given mode vars set."""
    for var in _MODE_VARS:
        os.environ.pop(var, None)
    os.environ.update(env)
    if "mcp_redmine_rd.server" in sys.modules:
        return importlib.reload(sys.modules["mcp_redmine_rd.server"])
    import mcp_redmine_rd.server as server
    return server


LOCAL_ENV = {"REDMINE_URL": "https://redmine.example.com", "REDMINE_API_KEY": "test-key"}
OAUTH_ENV = {
    "REDMINE_URL": "https://redmine.example.com",
    "REDMINE_CLIENT_ID": "c",
    "REDMINE_CLIENT_SECRET": "s",
}


@pytest.fixture
def restore_get_access_token():
    """Undo any get_access_token monkeypatching from injection tests."""
    yield
    from fastmcp.server.dependencies import get_access_token as real
    for name in ("tools", "resources", "prompts", "scopes"):
        importlib.import_module(f"mcp_redmine_rd.{name}").get_access_token = real


def test_local_mode_selected_by_api_key():
    server = _reimport_server(LOCAL_ENV)
    assert server.LOCAL_MODE is True
    assert server.redmine.api_key == "test-key"
    assert type(server.auth).__name__ == "LocalTokenVerifier"


def test_local_mode_binds_to_loopback():
    server = _reimport_server(LOCAL_ENV)
    assert server.MCP_HOST == "127.0.0.1"


def test_oauth_mode_when_no_api_key():
    server = _reimport_server(OAUTH_ENV)
    assert server.LOCAL_MODE is False
    assert type(server.auth).__name__ == "RedmineProvider"
    assert server.redmine.api_key is None


def test_inject_local_token_grants_full_scope_everywhere(restore_get_access_token):
    server = _reimport_server(LOCAL_ENV)
    server._inject_local_token()

    from mcp_redmine_rd.scopes import get_registered_scopes
    expected = set(get_registered_scopes())
    for name in ("tools", "resources", "prompts", "scopes"):
        mod = importlib.import_module(f"mcp_redmine_rd.{name}")
        token = mod.get_access_token()
        assert token is not None, f"{name}.get_access_token() returned None"
        assert set(token.scopes) == expected


def test_stdio_entrypoint_requires_api_key():
    """main_local_stdio must refuse to start in OAuth mode."""
    server = _reimport_server(OAUTH_ENV)
    with pytest.raises(SystemExit):
        server.main_local_stdio()
