"""Unit tests for LocalTokenVerifier (local API-key mode)."""

from __future__ import annotations

import pytest

from mcp_redmine_rd.auth import LocalTokenVerifier
from mcp_redmine_rd.scopes import VIEW_ISSUES


@pytest.mark.asyncio
async def test_local_verifier_accepts_expected_token():
    v = LocalTokenVerifier(expected_token="secret", scopes=[VIEW_ISSUES])
    token = await v.verify_token("secret")
    assert token is not None
    assert token.scopes == [VIEW_ISSUES]
    assert token.client_id == "local"


@pytest.mark.asyncio
async def test_local_verifier_rejects_wrong_token():
    v = LocalTokenVerifier(expected_token="secret", scopes=[VIEW_ISSUES])
    assert await v.verify_token("wrong") is None


@pytest.mark.asyncio
async def test_local_verifier_rejects_when_no_token_configured():
    """An empty expected token must not become an auth bypass."""
    v = LocalTokenVerifier(expected_token="", scopes=[VIEW_ISSUES])
    assert await v.verify_token("") is None


@pytest.mark.asyncio
async def test_local_verifier_grants_all_registered_scopes():
    scopes = ["view_issues", "edit_issues", "view_project"]
    v = LocalTokenVerifier(expected_token="local", scopes=scopes)
    token = await v.verify_token("local")
    assert token is not None
    assert token.scopes == scopes

    async def aclose_is_noop():
        await v.aclose()  # must not raise

    await aclose_is_noop()
