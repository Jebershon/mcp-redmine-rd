"""Async HTTP client for the Redmine REST API."""

from __future__ import annotations

from typing import Any

import httpx

# Attachments are fetched into memory, so cap what we are willing to pull.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Connections are pooled and reused across requests. Without this, every tool
# call paid for a fresh TCP + TLS handshake against Redmine.
DEFAULT_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)


class RedmineAPIError(Exception):
    """Base error for Redmine API failures."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class RedmineAuthError(RedmineAPIError):
    """401 Unauthorized — token is invalid or expired."""


class RedmineForbiddenError(RedmineAPIError):
    """403 Forbidden — user lacks permission for this action."""


class RedmineNotFoundError(RedmineAPIError):
    """404 Not Found — resource does not exist."""


class RedmineValidationError(RedmineAPIError):
    """422 Unprocessable Entity — validation failed (e.g. missing required fields)."""

    def __init__(self, status_code: int, message: str, errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(status_code, message)


class RedmineRateLimitError(RedmineAPIError):
    """429 Too Many Requests — Redmine is throttling us."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        suffix = f" Retry after {retry_after}s." if retry_after else ""
        super().__init__(429, f"Redmine rate limit exceeded.{suffix}")


class RedmineAttachmentTooLargeError(RedmineAPIError):
    """Attachment exceeds the size we are willing to pull into memory."""

    def __init__(self, size: int | None, limit: int):
        self.size = size
        self.limit = limit
        size_desc = f"{size / 1_048_576:.1f} MB" if size else "unknown size"
        super().__init__(
            413,
            f"Attachment is too large ({size_desc}); limit is "
            f"{limit / 1_048_576:.0f} MB.",
        )


class RedmineClient:
    """Thin async wrapper around Redmine's REST API.

    Each call requires a Bearer token so the client is stateless
    with respect to authentication. The underlying connection pool is
    shared across calls and must be released with `aclose()`.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        limits: httpx.Limits | None = None,
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # When set, every request authenticates with this Redmine API key and the
        # per-call `token` argument is ignored. When None, the per-call token is
        # sent as a Bearer header (used by the test suite).
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits or DEFAULT_LIMITS,
            # Redmine may redirect attachment downloads to a storage path.
            # httpx drops the Authorization header on cross-host redirects.
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        """Close the connection pool. Call once on server shutdown."""
        await self._client.aclose()

    async def get(
        self, path: str, token: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self._client.get(
            self._url(path), params=params, headers=self._headers(token)
        )
        self._raise_for_status(response)
        return response.json()

    async def post(
        self, path: str, token: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self._client.post(
            self._url(path),
            json=json,
            headers={**self._headers(token), "Content-Type": "application/json"},
        )
        self._raise_for_status(response)
        return response.json()

    async def put(
        self, path: str, token: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        response = await self._client.put(
            self._url(path),
            json=json,
            headers={**self._headers(token), "Content-Type": "application/json"},
        )
        self._raise_for_status(response)
        if response.status_code == 204:
            return None
        return response.json()

    async def get_binary(
        self,
        url: str,
        token: str,
        max_bytes: int = MAX_ATTACHMENT_BYTES,
    ) -> tuple[bytes, str]:
        """Download a binary resource (e.g. an issue attachment).

        Accepts an absolute URL — Redmine's `content_url` on an attachment is
        already fully qualified — or a path relative to the Redmine base URL.

        Returns (content, mime_type). Raises RedmineAttachmentTooLargeError
        rather than buffering an unbounded response into memory.
        """
        async with self._client.stream(
            "GET", self._url(url), headers=self._headers(token)
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                self._raise_for_status(response)

            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > max_bytes:
                raise RedmineAttachmentTooLargeError(int(declared), max_bytes)

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise RedmineAttachmentTooLargeError(None, max_bytes)
                chunks.append(chunk)

            mime_type = (
                response.headers.get("content-type", "application/octet-stream")
                .split(";")[0]
                .strip()
            )
            return b"".join(chunks), mime_type

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}{path}"

    def _headers(self, token: str) -> dict[str, str]:
        if self.api_key:
            return {"X-Redmine-API-Key": self.api_key}
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _error_detail(response: httpx.Response) -> list[str]:
        """Pull Redmine's `errors` array out of a failure body, if there is one."""
        try:
            body = response.json()
        except Exception:
            return []
        if isinstance(body, dict):
            errors = body.get("errors", [])
            if isinstance(errors, list):
                return [str(e) for e in errors]
        return []

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise RedmineAuthError(401, "Authentication failed — token may be expired.")
        if response.status_code == 403:
            raise RedmineForbiddenError(403, "Permission denied.")
        if response.status_code == 404:
            raise RedmineNotFoundError(404, "Resource not found in Redmine.")
        if response.status_code == 422:
            errors = RedmineClient._error_detail(response)
            raise RedmineValidationError(
                422,
                f"Validation failed: {'; '.join(errors) if errors else 'unknown error'}",
                errors=errors,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RedmineRateLimitError(
                int(retry_after) if retry_after and retry_after.isdigit() else None
            )
        if response.status_code >= 500:
            raise RedmineAPIError(
                response.status_code, f"Redmine server error ({response.status_code})."
            )
        # Catch-all. Without this, a 400 (malformed filter, bad status_id) fell
        # through and its error body was returned to the caller as if it were a
        # successful result — the model would then reason over Redmine's error
        # payload without ever being told the request failed.
        if response.status_code >= 400:
            errors = RedmineClient._error_detail(response)
            detail = f": {'; '.join(errors)}" if errors else "."
            raise RedmineAPIError(
                response.status_code,
                f"Redmine rejected the request ({response.status_code}){detail}",
            )
