"""Scope constants, decorator, and enforcement helpers for Redmine MCP tools.

A scope names the Redmine permission a tool needs. In local mode the client is
granted all registered scopes (the API key already scopes to the user's Redmine
role), so the decorator documents the requirement and gates unauthenticated calls.

Usage — declare scopes directly on each tool or resource:

    @mcp.tool()
    @requires_scopes(VIEW_ISSUES)
    async def get_issue_details(issue_id: int) -> str:
        ...  # auth + scope check handled by decorator

server.py collects all declared scopes automatically via get_registered_scopes().
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from mcp_redmine_rd.client import RedmineAPIError

# --- Scope constants ---

VIEW_PROJECT = "view_project"
VIEW_ISSUES = "view_issues"
SEARCH_PROJECT = "search_project"  # Required for /search.json and project-scoped search
VIEW_TIME_ENTRIES = "view_time_entries"  # Phase 4: list_time_entries
ADD_ISSUES = "add_issues"               # Phase 5: create_issue
EDIT_ISSUES = "edit_issues"             # Phase 5: update_issue
ADD_PROJECT = "add_project"             # Phase 5: create_project
EDIT_PROJECT = "edit_project"           # Phase 5: update_project
VIEW_WIKI_PAGES = "view_wiki_pages"     # Phase 5: get_wiki_page
EDIT_WIKI_PAGES = "edit_wiki_pages"     # Phase 5: update_wiki_page
RENAME_WIKI_PAGES = "rename_wiki_pages" # Phase 5: rename_wiki_page


# --- Global scope registry (populated at decoration time) ---

_registry: set[str] = set()


def get_registered_scopes() -> list[str]:
    """Return all scopes (Redmine permissions) declared via @requires_scopes.

    Call after register_tools()/register_resources() for the complete set. Used
    to grant the local token every scope the tools may need.
    """
    return sorted(_registry)


# --- Decorator ---


def requires_scopes(*scopes: str) -> Callable:
    """Declare the Redmine permissions a tool or resource needs.

    At decoration time: registers the scopes to the global registry so the local
    token can be granted all of them.

    At call time: checks that the request is authenticated and that the token has
    all required scopes; returns a descriptive error string otherwise.

    Usage::

        @mcp.tool()
        @requires_scopes(VIEW_ISSUES, SEARCH_PROJECT)
        async def search_issues(query: str) -> str:
            token = get_access_token()  # guaranteed non-None here
            ...
    """
    _registry.update(scopes)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = get_access_token()
            if token is None:
                return "Error: not authenticated."
            if scopes:
                if err := check_scope(token, *scopes):
                    return err
            try:
                return await fn(*args, **kwargs)
            except RedmineAPIError as e:
                # Tools handle the errors they can explain (403, 404, 422).
                # Anything left — 400, 429, 5xx — would otherwise be masked by
                # FastMCP into a generic "error calling tool", telling the model
                # nothing. Surface it as text it can actually act on.
                return f"Error: {e}"

        wrapper._required_scopes = list(scopes)  # type: ignore[attr-defined]
        return wrapper

    return decorator


# --- Enforcement helper (used internally by requires_scopes and by auth.py) ---


def check_scope(token: AccessToken, *required: str) -> str | None:
    """Return an error string if any required scope is missing, else None."""
    granted = set(token.scopes or [])
    missing = [s for s in required if s not in granted]
    if missing:
        return (
            f"Error: your Redmine account lacks the required permission(s): "
            f"{', '.join(missing)}."
        )
    return None
