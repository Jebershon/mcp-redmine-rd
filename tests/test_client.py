"""Unit tests for RedmineClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mcp_redmine_rd.client import (
    RedmineAPIError,
    RedmineAttachmentTooLargeError,
    RedmineAuthError,
    RedmineClient,
    RedmineForbiddenError,
    RedmineNotFoundError,
    RedmineRateLimitError,
    RedmineValidationError,
)


def _client_with_transport(handler) -> RedmineClient:
    """RedmineClient whose pool is backed by a mock transport."""
    client = RedmineClient(base_url="https://redmine.example.com")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _mock_response(status_code: int, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# --- _raise_for_status ---


def test_raise_for_status_401():
    resp = _mock_response(401)
    with pytest.raises(RedmineAuthError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 401


def test_raise_for_status_403():
    resp = _mock_response(403)
    with pytest.raises(RedmineForbiddenError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 403


def test_raise_for_status_404():
    resp = _mock_response(404)
    with pytest.raises(RedmineNotFoundError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 404


def test_raise_for_status_422_with_errors():
    resp = _mock_response(422, {"errors": ["Subject can't be blank", "Tracker is invalid"]})
    with pytest.raises(RedmineValidationError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 422
    assert "Subject can't be blank" in exc_info.value.errors
    assert "Tracker is invalid" in exc_info.value.errors
    assert "Subject can't be blank" in str(exc_info.value)


def test_raise_for_status_422_no_body():
    resp = _mock_response(422)
    resp.json.side_effect = Exception("no body")
    with pytest.raises(RedmineValidationError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 422
    assert exc_info.value.errors == []


def test_raise_for_status_500():
    resp = _mock_response(500)
    with pytest.raises(RedmineAPIError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 500


def test_raise_for_status_200_no_error():
    resp = _mock_response(200)
    RedmineClient._raise_for_status(resp)  # should not raise


def test_raise_for_status_204_no_error():
    resp = _mock_response(204)
    RedmineClient._raise_for_status(resp)  # should not raise


def test_raise_for_status_400_does_not_fall_through():
    """A 400 must raise, not hand Redmine's error body back as a success payload."""
    resp = _mock_response(400, {"errors": ["Invalid status_id"]})
    with pytest.raises(RedmineAPIError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 400
    assert "Invalid status_id" in str(exc_info.value)


def test_raise_for_status_400_without_error_body():
    resp = _mock_response(400)
    resp.json.side_effect = Exception("no body")
    with pytest.raises(RedmineAPIError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 400


def test_raise_for_status_429_with_retry_after():
    resp = _mock_response(429)
    resp.headers = {"retry-after": "30"}
    with pytest.raises(RedmineRateLimitError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.retry_after == 30
    assert "30s" in str(exc_info.value)


def test_raise_for_status_429_without_retry_after():
    resp = _mock_response(429)
    resp.headers = {}
    with pytest.raises(RedmineRateLimitError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.retry_after is None


def test_raise_for_status_409_conflict_raises():
    """Any unhandled 4xx must surface, not pass silently."""
    resp = _mock_response(409)
    resp.json.side_effect = Exception("no body")
    with pytest.raises(RedmineAPIError) as exc_info:
        RedmineClient._raise_for_status(resp)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_raises_on_400_rather_than_returning_error_body():
    """End-to-end: the caller gets an exception, not {"errors": [...]}."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": ["Invalid status_id"]})

    client = _client_with_transport(handler)
    with pytest.raises(RedmineAPIError):
        await client.get("/issues.json", token="tok", params={"status_id": "bogus"})
    await client.aclose()


# --- client construction ---


def test_client_strips_trailing_slash():
    client = RedmineClient(base_url="https://redmine.example.com/")
    assert client.base_url == "https://redmine.example.com"


def test_client_default_timeout():
    client = RedmineClient(base_url="https://redmine.example.com")
    assert client.timeout == 30.0


def test_client_custom_timeout():
    client = RedmineClient(base_url="https://redmine.example.com", timeout=10.0)
    assert client.timeout == 10.0


# --- _url ---


def test_url_prefixes_relative_path_with_base():
    client = RedmineClient(base_url="https://redmine.example.com")
    assert client._url("/issues/1.json") == "https://redmine.example.com/issues/1.json"


def test_url_passes_absolute_url_through():
    """Attachment content_url comes back from Redmine already fully qualified."""
    client = RedmineClient(base_url="https://redmine.example.com")
    absolute = "https://redmine.example.com/attachments/download/7/shot.png"
    assert client._url(absolute) == absolute


# --- get_binary ---


@pytest.mark.asyncio
async def test_get_binary_returns_content_and_mime_type():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"}
        )

    client = _client_with_transport(handler)
    content, mime_type = await client.get_binary(
        "https://redmine.example.com/attachments/download/7/shot.png", token="tok"
    )
    assert content == b"\x89PNG\r\n"
    assert mime_type == "image/png"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_binary_strips_charset_from_mime_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"x", headers={"content-type": "image/png; charset=binary"}
        )

    client = _client_with_transport(handler)
    _, mime_type = await client.get_binary("/attachments/download/7", token="tok")
    assert mime_type == "image/png"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_binary_rejects_oversized_declared_length():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 100,
            headers={"content-type": "image/png", "content-length": "100"},
        )

    client = _client_with_transport(handler)
    with pytest.raises(RedmineAttachmentTooLargeError):
        await client.get_binary("/attachments/download/7", token="tok", max_bytes=50)
    await client.aclose()


@pytest.mark.asyncio
async def test_get_binary_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client_with_transport(handler)
    with pytest.raises(RedmineNotFoundError):
        await client.get_binary("/attachments/download/999", token="tok")
    await client.aclose()


# --- api-key auth mode ---


def test_headers_use_bearer_by_default():
    client = RedmineClient(base_url="https://redmine.example.com")
    assert client._headers("tok") == {"Authorization": "Bearer tok"}


def test_headers_use_api_key_when_configured():
    """Local mode: the per-call token is ignored in favour of the API key."""
    client = RedmineClient(base_url="https://redmine.example.com", api_key="abc123")
    assert client._headers("ignored") == {"X-Redmine-API-Key": "abc123"}
