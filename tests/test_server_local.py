"""Tests for the local (stdio / API-key) server wiring."""

from __future__ import annotations

import importlib
import os
import sys

import pytest

# Env vars server.py reads at import time.
_MODE_VARS = ("REDMINE_URL", "REDMINE_API_KEY")


def _reimport_server(env: dict[str, str]):
    """(Re)import server.py with exactly the given env vars set."""
    for var in _MODE_VARS:
        os.environ.pop(var, None)
    os.environ.update(env)
    if "mcp_redmine_rd.server" in sys.modules:
        return importlib.reload(sys.modules["mcp_redmine_rd.server"])
    import mcp_redmine_rd.server as server
    return server


LOCAL_ENV = {"REDMINE_URL": "https://redmine.example.com", "REDMINE_API_KEY": "test-key"}


@pytest.fixture
def restore_get_access_token():
    """Undo any get_access_token monkeypatching from injection tests."""
    yield
    from fastmcp.server.dependencies import get_access_token as real
    for name in ("tools", "resources", "prompts", "scopes"):
        importlib.import_module(f"mcp_redmine_rd.{name}").get_access_token = real


def test_client_uses_api_key():
    server = _reimport_server(LOCAL_ENV)
    assert server.redmine.api_key == "test-key"


def test_http_auth_is_local_token_verifier():
    server = _reimport_server(LOCAL_ENV)
    assert type(server.auth).__name__ == "LocalTokenVerifier"


def test_binds_to_loopback_by_default():
    server = _reimport_server(LOCAL_ENV)
    assert server.MCP_HOST == "127.0.0.1"


def test_api_key_is_required():
    """Without REDMINE_API_KEY the server cannot start."""
    for var in _MODE_VARS:
        os.environ.pop(var, None)
    os.environ["REDMINE_URL"] = "https://redmine.example.com"
    with pytest.raises(KeyError):
        if "mcp_redmine_rd.server" in sys.modules:
            importlib.reload(sys.modules["mcp_redmine_rd.server"])
        else:  # pragma: no cover - import path when run in isolation
            import mcp_redmine_rd.server  # noqa: F401


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
