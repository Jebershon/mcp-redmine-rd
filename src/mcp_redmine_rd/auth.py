"""Auth for the local single-user Redmine MCP server.

There is no OAuth: the RedmineClient authenticates to Redmine with a configured
API key. Over stdio there is no auth at all (the local process is the trust
boundary). Over HTTP, LocalTokenVerifier gates the server with one pre-shared
token and grants the full set of registered scopes.
"""

from __future__ import annotations

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class LocalTokenVerifier(TokenVerifier):
    """Gate the local HTTP server with a single pre-shared token.

    The API key held by the RedmineClient already carries the user's Redmine
    permissions, so this verifier only checks that the MCP client presented the
    expected local token and grants all registered scopes so the scope decorators
    pass. Intended for a localhost, single-user deployment.
    """

    def __init__(self, *, expected_token: str, scopes: list[str]):
        super().__init__()
        self._expected_token = expected_token
        self._scopes = scopes

    async def aclose(self) -> None:  # symmetry with the lifespan shutdown; nothing to close
        return None

    async def verify_token(self, token: str) -> AccessToken | None:
        if not self._expected_token or token != self._expected_token:
            return None
        return AccessToken(
            token=token,
            client_id="local",
            scopes=self._scopes,
            expires_at=None,
            claims={"sub": "local"},
        )
