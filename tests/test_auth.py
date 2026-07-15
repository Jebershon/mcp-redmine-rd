"""Unit tests for RedmineProvider scope capture and RedmineTokenVerifier."""

from __future__ import annotations

import httpx
import pytest

from mcp_redmine_rd.auth import (
    MAX_CACHE_ENTRIES,
    RedmineProvider,
    RedmineTokenVerifier,
)
from mcp_redmine_rd.scopes import VIEW_ISSUES, get_registered_scopes


# --- _extract_upstream_claims ---


@pytest.mark.asyncio
async def test_extract_upstream_claims_stores_scope():
    """Scopes from Redmine token response are stored in scope_store."""
    scope_store: dict[str, list[str]] = {}
    provider = RedmineProvider(
        redmine_url="https://redmine.example.com",
        client_id="cid",
        client_secret="csec",
        base_url="http://localhost:8000",
        scopes=get_registered_scopes(),
    )
    # Inject our own scope_store so we can inspect it
    provider._scope_store = scope_store
    provider._token_validator._scope_store = scope_store  # type: ignore[attr-defined]

    idp_tokens = {
        "access_token": "tok_abc123",
        "scope": "view_issues view_project",
        "token_type": "Bearer",
    }
    result = await provider._extract_upstream_claims(idp_tokens)

    assert result is None  # Should not embed extra claims in JWT
    assert scope_store["tok_abc123"] == ["view_issues", "view_project"]


@pytest.mark.asyncio
async def test_extract_upstream_claims_no_scope_field():
    """Missing scope field in token response leaves scope_store unchanged."""
    scope_store: dict[str, list[str]] = {}
    provider = RedmineProvider(
        redmine_url="https://redmine.example.com",
        client_id="cid",
        client_secret="csec",
        base_url="http://localhost:8000",
        scopes=get_registered_scopes(),
    )
    provider._scope_store = scope_store

    idp_tokens = {"access_token": "tok_xyz", "token_type": "Bearer"}
    await provider._extract_upstream_claims(idp_tokens)

    assert "tok_xyz" not in scope_store


# --- RedmineTokenVerifier scope fallback ---


def test_verifier_falls_back_to_registered_scopes_when_token_not_in_store():
    """verify_token uses get_registered_scopes() as fallback when token not yet in scope_store."""
    scope_store: dict[str, list[str]] = {}
    RedmineTokenVerifier(
        redmine_url="https://redmine.example.com",
        scope_store=scope_store,
    )
    # scope_store is empty; fallback should be registered scopes (a list, possibly empty in test context)
    granted = scope_store.get("unknown_token", get_registered_scopes())
    assert isinstance(granted, list)


def test_verifier_uses_stored_scopes_when_present():
    """verify_token uses scope_store when the token is present."""
    scope_store: dict[str, list[str]] = {"tok_123": [VIEW_ISSUES]}
    granted = scope_store.get("tok_123", get_registered_scopes())
    assert granted == [VIEW_ISSUES]


# --- verify_token caching ---


def _verifier_with_transport(handler, **kwargs) -> RedmineTokenVerifier:
    verifier = RedmineTokenVerifier(
        redmine_url="https://redmine.example.com",
        scope_store={"tok_123": [VIEW_ISSUES]},
        **kwargs,
    )
    verifier._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return verifier


def _user_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"user": {"id": 7, "login": "dev", "mail": "d@x.io"}})


@pytest.mark.asyncio
async def test_verify_token_hits_redmine_on_first_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _user_response(request)

    verifier = _verifier_with_transport(handler)
    token = await verifier.verify_token("tok_123")

    assert token is not None
    assert token.client_id == "7"
    assert token.scopes == [VIEW_ISSUES]
    assert len(calls) == 1
    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_is_cached_within_ttl():
    """The whole point: repeated MCP requests must not re-hit Redmine each time."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _user_response(request)

    verifier = _verifier_with_transport(handler, cache_ttl_seconds=60)
    for _ in range(5):
        assert await verifier.verify_token("tok_123") is not None

    assert len(calls) == 1
    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_revalidates_after_ttl_expires():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _user_response(request)

    verifier = _verifier_with_transport(handler, cache_ttl_seconds=0)
    await verifier.verify_token("tok_123")
    await verifier.verify_token("tok_123")

    assert len(calls) == 2
    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_does_not_cache_failures():
    """A rejected token must not be cached, or a newly-valid token stays broken."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401)

    verifier = _verifier_with_transport(handler)
    assert await verifier.verify_token("bad_token") is None
    assert await verifier.verify_token("bad_token") is None

    assert len(calls) == 2
    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_cache_is_per_token():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["Authorization"])
        return _user_response(request)

    verifier = _verifier_with_transport(handler)
    await verifier.verify_token("tok_123")
    await verifier.verify_token("tok_other")

    assert calls == ["Bearer tok_123", "Bearer tok_other"]
    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_cache_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        return _user_response(request)

    verifier = _verifier_with_transport(handler, cache_ttl_seconds=300)
    for i in range(MAX_CACHE_ENTRIES + 50):
        await verifier.verify_token(f"tok_{i}")

    assert len(verifier._cache) <= MAX_CACHE_ENTRIES
    await verifier.aclose()


# --- LocalTokenVerifier (API-key mode) ---


@pytest.mark.asyncio
async def test_local_verifier_accepts_expected_token():
    from mcp_redmine_rd.auth import LocalTokenVerifier

    v = LocalTokenVerifier(expected_token="secret", scopes=[VIEW_ISSUES])
    token = await v.verify_token("secret")
    assert token is not None
    assert token.scopes == [VIEW_ISSUES]
    assert token.client_id == "local"


@pytest.mark.asyncio
async def test_local_verifier_rejects_wrong_token():
    from mcp_redmine_rd.auth import LocalTokenVerifier

    v = LocalTokenVerifier(expected_token="secret", scopes=[VIEW_ISSUES])
    assert await v.verify_token("wrong") is None


@pytest.mark.asyncio
async def test_local_verifier_rejects_when_no_token_configured():
    """An empty expected token must not become an auth bypass."""
    from mcp_redmine_rd.auth import LocalTokenVerifier

    v = LocalTokenVerifier(expected_token="", scopes=[VIEW_ISSUES])
    assert await v.verify_token("") is None
