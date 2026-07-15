"""Entry point for the single-user local Redmine MCP server.

Authenticates to Redmine with your API key. Run over stdio (recommended, launched
on demand by the MCP client) via `main_local_stdio`, or over HTTP via `main`.
"""

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

from mcp_redmine_rd.auth import LocalTokenVerifier
from mcp_redmine_rd.client import RedmineClient
from mcp_redmine_rd.prompts import register_prompts
from mcp_redmine_rd.resources import register_resources
from mcp_redmine_rd.scopes import get_registered_scopes
from mcp_redmine_rd.tools import register_tools

load_dotenv()

# Required configuration
REDMINE_URL = os.environ["REDMINE_URL"]
REDMINE_API_KEY = os.environ["REDMINE_API_KEY"]  # Redmine → My account → API access key

# Token the MCP client must present in HTTP mode (Bearer). Loopback-only by
# default; change MCP_LOCAL_TOKEN and bind carefully if you expose the port.
MCP_LOCAL_TOKEN = os.environ.get("MCP_LOCAL_TOKEN", "local")

# Optional configuration.
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
CORS_ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")

# Redmine REST client — pooled connection, authenticates every call with the API
# key. Closed on shutdown.
redmine = RedmineClient(base_url=REDMINE_URL, api_key=REDMINE_API_KEY)


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await redmine.aclose()


mcp = FastMCP(
    name="RapidData Redmine MCP",
    version=version("mcp-redmine-rd"),
    instructions="MCP server for interacting with Redmine project management.",
    lifespan=lifespan,
)

# Register the MCP surface — @requires_scopes decorators populate the scope
# registry as a side effect, so this must run before the verifier is built.
register_tools(mcp, redmine)
register_resources(mcp, redmine)
register_prompts(mcp, redmine)

# HTTP transport gates access with a single local token and grants all scopes;
# the API key already scopes to the user's Redmine permissions.
auth = LocalTokenVerifier(
    expected_token=MCP_LOCAL_TOKEN,
    scopes=get_registered_scopes(),
)
mcp.auth = auth


def _inject_local_token() -> None:
    """Supply a full-scope access token to the tool modules for stdio mode.

    Stdio has no HTTP Authorization header, so FastMCP's get_access_token() would
    return None and every @requires_scopes tool would refuse to run. The API key
    already authenticates to Redmine, so the token value is unused — we just need
    the scope decorators to see an authenticated, full-scope token. This mirrors
    what the integration tests inject.
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
    """Entry point for local mode over stdio.

    Lets an MCP client (e.g. Claude Code) launch the server on demand with no
    port and no bearer token — the easiest way to run and share it per-developer.
    """
    mcp.auth = None  # stdio does not authenticate; the local process is the boundary
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
