"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

import mcp_redmine_rd.tools as tools_module


@pytest.fixture(autouse=True)
def _clear_custom_field_cache():
    """Reset the module-level custom-field name->id cache between tests.

    The cache is global by design (shared across users at runtime), so without
    this a test that populates it leaks the resolved names into later tests —
    masking, for example, the admin-only-lookup fallback path.
    """
    tools_module._custom_field_names = None
    yield
    tools_module._custom_field_names = None
