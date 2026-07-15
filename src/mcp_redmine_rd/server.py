"""FastMCP server entry point for the Redmine MCP server."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from mcp_redmine_rd.auth import (
    DEFAULT_CACHE_TTL_SECONDS,
    LocalTokenVerifier,
    RedmineProvider,
)
from mcp_redmine_rd.client import RedmineClient
from mcp_redmine_rd.prompts import register_prompts
from mcp_redmine_rd.resources import register_resources
from mcp_redmine_rd.scopes import (
    get_effective_scopes,
    get_registered_scopes,
    set_allowed_scopes,
)
from mcp_redmine_rd.tools import register_tools

load_dotenv()

# Required configuration
REDMINE_URL = os.environ["REDMINE_URL"]

# Auth mode. Setting REDMINE_API_KEY selects single-user local mode: the server
# talks to Redmine with that API key and skips OAuth entirely — useful when you
# are not a Redmine admin and cannot register an OAuth application. Otherwise the
# server runs the centralized OAuth flow, which needs client credentials.
REDMINE_API_KEY = os.environ.get("REDMINE_API_KEY")
LOCAL_MODE = bool(REDMINE_API_KEY)

if not LOCAL_MODE:
    REDMINE_CLIENT_ID = os.environ["REDMINE_CLIENT_ID"]
    REDMINE_CLIENT_SECRET = os.environ["REDMINE_CLIENT_SECRET"]

# Token the MCP client must present in local mode (Bearer). Localhost-only by
# default; change MCP_LOCAL_TOKEN and bind carefully if you expose the port.
MCP_LOCAL_TOKEN = os.environ.get("MCP_LOCAL_TOKEN", "local")

# Optional configuration. Local mode binds to loopback by default.
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1" if LOCAL_MODE else "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", f"http://localhost:{MCP_PORT}")
TOKEN_CACHE_TTL = float(
    os.environ.get("TOKEN_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)
)
CORS_ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")

# Redmine REST client — holds a pooled connection to Redmine, closed on shutdown.
# In local mode it authenticates every call with the API key.
redmine = RedmineClient(base_url=REDMINE_URL, api_key=REDMINE_API_KEY)


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await redmine.aclose()
        await auth.aclose()


# FastMCP server (auth added after tool registration so scopes can be auto-collected)
mcp = FastMCP(
    name="RapidData Redmine MCP",
    version=version("mcp-redmine-rd"),
    instructions="MCP server for interacting with Redmine project management.",
    lifespan=lifespan,
)

# Register MCP surface — @requires_scopes decorators populate the scope registry as a side effect
register_tools(mcp, redmine)
register_resources(mcp, redmine)
register_prompts(mcp, redmine)

# Optional: filter requested scopes to match what the Redmine OAuth app supports
REDMINE_SCOPES = os.environ.get("REDMINE_SCOPES")
if REDMINE_SCOPES:
    set_allowed_scopes(REDMINE_SCOPES.split())

# Auth provider — scopes auto-collected from @requires_scopes.
if LOCAL_MODE:
    # Single-user local mode: the API key already scopes to the user's Redmine
    # permissions, so grant all registered scopes and just gate the local token.
    auth = LocalTokenVerifier(
        expected_token=MCP_LOCAL_TOKEN,
        scopes=get_registered_scopes(),
    )
else:
    auth = RedmineProvider(
        redmine_url=REDMINE_URL,
        client_id=REDMINE_CLIENT_ID,
        client_secret=REDMINE_CLIENT_SECRET,
        base_url=MCP_BASE_URL,
        scopes=get_effective_scopes(),
        cache_ttl_seconds=TOKEN_CACHE_TTL,
    )
mcp.auth = auth


def _inject_local_token() -> None:
    """Supply a full-scope access token to the tool modules for stdio mode.

    Stdio has no HTTP Authorization header, so FastMCP's get_access_token() would
    return None and every @requires_scopes tool would refuse to run. In local mode
    the RedmineClient already authenticates with the API key, so the token value is
    unused — we just need the scope decorators to see an authenticated token with
    all scopes. This mirrors exactly what the integration tests inject.
    """
    import importlib

    from fastmcp.server.auth import AccessToken

    dummy = AccessToken(
        token="local",
        client_id="local",
        scopes=get_registered_scopes(),
        expires_at=None,
        claims={"sub": "local"},
    )
    for module_name in ("tools", "resources", "prompts", "scopes"):
        module = importlib.import_module(f"mcp_redmine_rd.{module_name}")
        if hasattr(module, "get_access_token"):
            module.get_access_token = lambda: dummy


def main_local_stdio() -> None:
    """Entry point for single-user local mode over stdio.

    Requires REDMINE_API_KEY. Lets an MCP client (e.g. Claude Code) launch the
    server on demand with no port, no OAuth, and no bearer token — the easiest
    way to run and share the server per-developer.
    """
    if not LOCAL_MODE:
        raise SystemExit(
            "stdio local mode requires REDMINE_API_KEY to be set "
            "(get it from Redmine → My account → API access key)."
        )
    mcp.auth = None  # stdio does not authenticate; access is the local process itself
    _inject_local_token()
    asyncio.run(mcp.run_stdio_async())


def main() -> None:
    asyncio.run(
        mcp.run_http_async(
            host=MCP_HOST,
            port=MCP_PORT,
            transport="streamable-http",
            middleware=[
                Middleware(
                    CORSMiddleware,
                    allow_origins=CORS_ALLOW_ORIGINS,
                    allow_methods=["*"],
                    allow_headers=["*"],
                    expose_headers=["Mcp-Session-Id"],
                ),
            ],
        )
    )


if __name__ == "__main__":
    main()
