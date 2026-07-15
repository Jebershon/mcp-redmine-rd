"""Unit tests for MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mcp_redmine_rd.client import RedmineForbiddenError
from mcp_redmine_rd.tools import (
    MAX_JOURNAL_ENTRIES,
    CustomFieldError,
    _build_custom_fields,
    _coerce_custom_value,
    _format_created_issue,
    _format_created_project,
    _format_issue,
    _format_issue_list,
    _format_project,
    _format_relations,
    _format_search_results,
    _format_time_entries,
    _format_versions,
    _format_wiki_page,
)


# --- search_issues formatting ---


def test_format_search_results_empty():
    data = {"results": [], "total_count": 0, "offset": 0, "limit": 25}
    assert _format_search_results(data) == "No issues found matching the query."


def test_format_search_results_basic():
    data = {
        "results": [
            {
                "id": 1,
                "title": "Bug #42: Login fails",
                "url": "/issues/42",
                "description": "Users cannot log in",
                "datetime": "2025-01-15T10:00:00Z",
            }
        ],
        "total_count": 1,
        "offset": 0,
        "limit": 25,
    }
    result = _format_search_results(data)
    assert "1 result(s)" in result
    assert "Bug #42: Login fails" in result
    assert "2025-01-15" in result
    assert "/issues/42" in result


def test_format_search_results_pagination():
    data = {
        "results": [{"title": f"Issue #{i}", "url": f"/issues/{i}"} for i in range(25)],
        "total_count": 50,
        "offset": 0,
        "limit": 25,
    }
    result = _format_search_results(data)
    assert "50 result(s)" in result
    assert "offset=25" in result


def test_format_search_results_with_offset():
    data = {
        "results": [{"title": "Issue #26", "url": "/issues/26"}],
        "total_count": 50,
        "offset": 25,
        "limit": 25,
    }
    result = _format_search_results(data)
    assert "26–26" in result


def test_format_search_results_truncates_long_descriptions():
    data = {
        "results": [
            {
                "title": "Long issue",
                "url": "/issues/1",
                "description": "x" * 300,
            }
        ],
        "total_count": 1,
        "offset": 0,
        "limit": 25,
    }
    result = _format_search_results(data)
    assert "…" in result
    assert "x" * 201 not in result


# --- journal truncation ---


def test_format_issue_truncates_journals():
    journals = [
        {"user": {"name": f"User {i}"}, "created_on": "2025-01-01", "notes": f"Note {i}"}
        for i in range(40)
    ]
    issue = {
        "id": 1,
        "subject": "Test",
        "journals": journals,
    }
    result = _format_issue(issue)
    assert f"Note {MAX_JOURNAL_ENTRIES - 1}" in result
    assert f"Note {MAX_JOURNAL_ENTRIES}" not in result
    assert "15 more entries (truncated)" in result


def test_format_issue_no_truncation_under_limit():
    journals = [
        {"user": {"name": "Alice"}, "created_on": "2025-01-01", "notes": "Hello"}
        for _ in range(5)
    ]
    issue = {"id": 1, "subject": "Test", "journals": journals}
    result = _format_issue(issue)
    assert "truncated" not in result


# --- format_issue basic ---


def test_format_issue_minimal():
    issue = {"id": 42, "subject": "Test issue"}
    result = _format_issue(issue)
    assert "# Issue #42 — Test issue" in result


def test_format_issue_custom_fields():
    """Field IDs must be shown — they are the fallback for writing a field back
    when the user lacks the admin rights needed to resolve names."""
    issue = {
        "id": 1,
        "subject": "With fields",
        "custom_fields": [{"id": 3, "name": "Severity", "value": "High"}],
    }
    result = _format_issue(issue)
    assert "**Severity** (id=3): High" in result


def test_format_issue_multi_value_custom_field():
    issue = {
        "id": 1,
        "subject": "With fields",
        "custom_fields": [{"id": 4, "name": "Platforms", "value": ["iOS", "Android"]}],
    }
    result = _format_issue(issue)
    assert "**Platforms** (id=4): iOS, Android" in result


def test_format_issue_full_fields():
    issue = {
        "id": 10,
        "subject": "Full issue",
        "project": {"name": "Alpha"},
        "tracker": {"name": "Bug"},
        "status": {"name": "In Progress"},
        "priority": {"name": "High"},
        "author": {"name": "Alice"},
        "assigned_to": {"name": "Bob"},
        "created_on": "2025-01-01T00:00:00Z",
        "updated_on": "2025-01-02T00:00:00Z",
    }
    result = _format_issue(issue)
    assert "**Project:** Alpha" in result
    assert "**Tracker:** Bug" in result
    assert "**Status:** In Progress" in result
    assert "**Priority:** High" in result
    assert "**Author:** Alice" in result
    assert "**Assigned to:** Bob" in result


def test_format_issue_description():
    issue = {
        "id": 1,
        "subject": "With desc",
        "description": "This is the bug description.",
    }
    result = _format_issue(issue)
    assert "## Description" in result
    assert "This is the bug description." in result


def test_format_issue_journals():
    issue = {
        "id": 1,
        "subject": "With journals",
        "journals": [
            {
                "user": {"name": "Alice"},
                "created_on": "2025-01-01",
                "notes": "First comment",
                "details": [],
            },
            {
                "user": {"name": "Bob"},
                "created_on": "2025-01-02",
                "notes": "",
                "details": [
                    {"name": "status_id", "old_value": "1", "new_value": "2"},
                ],
            },
        ],
    }
    result = _format_issue(issue)
    assert "## Journal / Comments" in result
    assert "### Alice — 2025-01-01" in result
    assert "First comment" in result
    assert "### Bob — 2025-01-02" in result
    assert "status_id: 1 → 2" in result


def test_format_issue_empty_journals_skipped():
    issue = {
        "id": 1,
        "subject": "Empty journal",
        "journals": [
            {"user": {"name": "Alice"}, "created_on": "2025-01-01", "notes": "", "details": []},
        ],
    }
    result = _format_issue(issue)
    assert "### Alice" not in result


# --- list_issues formatting ---


def test_format_issue_list_empty():
    data = {"issues": [], "total_count": 0, "offset": 0, "limit": 25}
    assert _format_issue_list(data) == "No issues found matching the filters."


def test_format_issue_list_basic():
    data = {
        "issues": [
            {
                "id": 42,
                "subject": "Fix login bug",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "assigned_to": {"name": "Alice"},
                "updated_on": "2025-06-15T10:00:00Z",
            },
            {
                "id": 43,
                "subject": "Add dark mode",
                "status": {"name": "New"},
                "priority": {"name": "Normal"},
                "updated_on": "2025-06-14T08:00:00Z",
            },
        ],
        "total_count": 2,
        "offset": 0,
        "limit": 25,
    }
    result = _format_issue_list(data)
    assert "2 issue(s)" in result
    assert "**#42** Fix login bug" in result
    assert "Status: In Progress" in result
    assert "Priority: High" in result
    assert "Assigned: Alice" in result
    assert "**#43** Add dark mode" in result
    assert "Assigned: Unassigned" in result


def test_format_issue_list_pagination():
    data = {
        "issues": [{"id": i, "subject": f"Issue {i}"} for i in range(25)],
        "total_count": 50,
        "offset": 0,
        "limit": 25,
    }
    result = _format_issue_list(data)
    assert "50 issue(s)" in result
    assert "offset=25" in result


def test_format_issue_list_no_pagination_when_all_shown():
    data = {
        "issues": [{"id": 1, "subject": "Only issue"}],
        "total_count": 1,
        "offset": 0,
        "limit": 25,
    }
    result = _format_issue_list(data)
    assert "offset=" not in result


# --- get_issue_relations formatting ---


def test_format_relations_empty():
    assert _format_relations(42, {"relations": []}) == "Issue #42 has no relations."


def test_format_relations_outgoing():
    data = {
        "relations": [
            {"relation_type": "blocks", "issue_id": 42, "issue_to_id": 99},
        ]
    }
    result = _format_relations(42, data)
    assert "**blocks** → #99" in result


def test_format_relations_incoming():
    data = {
        "relations": [
            {"relation_type": "blocks", "issue_id": 10, "issue_to_id": 42},
        ]
    }
    result = _format_relations(42, data)
    assert "**blocks** ← #10" in result


def test_format_relations_with_delay():
    data = {
        "relations": [
            {"relation_type": "precedes", "issue_id": 42, "issue_to_id": 43, "delay": 3},
        ]
    }
    result = _format_relations(42, data)
    assert "Delay: 3 day(s)" in result


# --- get_project_details formatting ---


def test_format_project_empty():
    assert _format_project({"project": {}}) == "Error: could not retrieve project details."


def test_format_project_basic():
    data = {
        "project": {
            "id": 1,
            "name": "Alpha",
            "identifier": "alpha",
            "status": 1,
            "created_on": "2024-01-01",
            "updated_on": "2025-01-01",
            "description": "Main project",
        }
    }
    result = _format_project(data)
    assert "# Alpha" in result
    assert "**Identifier:** alpha" in result
    assert "**Status:** active" in result
    assert "Main project" in result


def test_format_project_with_includes():
    data = {
        "project": {
            "id": 1,
            "name": "Alpha",
            "identifier": "alpha",
            "status": 1,
            "created_on": "2024-01-01",
            "updated_on": "2025-01-01",
            "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Feature"}],
            "issue_categories": [{"id": 10, "name": "Backend"}],
            "enabled_modules": [{"name": "issue_tracking"}, {"name": "wiki"}],
        }
    }
    result = _format_project(data)
    assert "## Trackers" in result
    assert "Bug (id=1)" in result
    assert "## Issue Categories" in result
    assert "Backend (id=10)" in result
    assert "## Enabled Modules" in result
    assert "issue_tracking" in result
    assert "wiki" in result


def test_format_project_closed_status():
    data = {
        "project": {
            "id": 1, "name": "Old", "identifier": "old",
            "status": 5, "created_on": "2024-01-01", "updated_on": "2025-01-01",
        }
    }
    result = _format_project(data)
    assert "closed/archived" in result


# --- get_project_versions formatting ---


def test_format_versions_empty():
    assert _format_versions("alpha", {"versions": []}) == "No versions found for project 'alpha'."


def test_format_versions_basic():
    data = {
        "versions": [
            {
                "id": 1,
                "name": "v1.0",
                "status": "open",
                "due_date": "2025-12-31",
                "sharing": "none",
                "description": "First release",
            },
            {
                "id": 2,
                "name": "v2.0",
                "status": "locked",
                "due_date": None,
                "sharing": "hierarchy",
                "description": "",
            },
        ]
    }
    result = _format_versions("alpha", data)
    assert "Versions for 'alpha'" in result
    assert "**v1.0** (id=1, status: open)" in result
    assert "Due: 2025-12-31" in result
    assert "First release" in result
    assert "**v2.0** (id=2, status: locked)" in result


# --- list_time_entries formatting ---


def test_format_time_entries_empty():
    data = {"time_entries": [], "total_count": 0, "offset": 0, "limit": 25}
    assert _format_time_entries(data) == "No time entries found."


def test_format_time_entries_basic():
    data = {
        "time_entries": [
            {
                "id": 1,
                "user": {"name": "Alice"},
                "project": {"name": "Alpha"},
                "issue": {"id": 42},
                "hours": 2.5,
                "activity": {"name": "Development"},
                "spent_on": "2025-06-15",
                "comments": "Fixed login bug",
            },
            {
                "id": 2,
                "user": {"name": "Bob"},
                "project": {"name": "Alpha"},
                "hours": 1.0,
                "activity": {"name": "Review"},
                "spent_on": "2025-06-15",
                "comments": "",
            },
        ],
        "total_count": 2,
        "offset": 0,
        "limit": 25,
    }
    result = _format_time_entries(data)
    assert "2 time entry/entries" in result
    assert "3.50 hours on this page" in result
    assert "**2.50h** — Alice on 2025-06-15 (issue #42)" in result
    assert "Development" in result
    assert '"Fixed login bug"' in result
    assert "**1.00h** — Bob on 2025-06-15" in result
    assert "issue #" not in result.split("Bob")[1]  # Bob has no issue


def test_format_time_entries_pagination():
    data = {
        "time_entries": [
            {"id": i, "user": {"name": "User"}, "hours": 1.0, "spent_on": "2025-01-01"}
            for i in range(25)
        ],
        "total_count": 50,
        "offset": 0,
        "limit": 25,
    }
    result = _format_time_entries(data)
    assert "offset=25" in result


def test_format_time_entries_long_comment_truncated():
    data = {
        "time_entries": [
            {
                "id": 1,
                "user": {"name": "Alice"},
                "hours": 1.0,
                "spent_on": "2025-01-01",
                "comments": "x" * 200,
            }
        ],
        "total_count": 1,
        "offset": 0,
        "limit": 25,
    }
    result = _format_time_entries(data)
    assert "…" in result


# --- create_issue formatting ---


def test_format_created_issue_basic():
    data = {
        "issue": {
            "id": 99,
            "subject": "New bug",
            "project": {"name": "Alpha"},
        }
    }
    result = _format_created_issue(data)
    assert "Issue #99 created successfully" in result
    assert "Alpha" in result
    assert "New bug" in result


def test_format_created_issue_empty():
    assert "response was empty" in _format_created_issue({"issue": {}})


# --- update_issue (no formatter — just string response) ---
# Tested via integration with the tool; the formatter is inline.


# --- create_project formatting ---


def test_format_created_project_basic():
    data = {
        "project": {
            "id": 7,
            "name": "New Project",
            "identifier": "new-project",
        }
    }
    result = _format_created_project(data)
    assert "New Project" in result
    assert "new-project" in result
    assert "id=7" in result
    assert "created successfully" in result


def test_format_created_project_empty():
    assert "response was empty" in _format_created_project({"project": {}})


# --- wiki page formatting ---


def test_format_wiki_page_empty():
    assert "could not retrieve" in _format_wiki_page({"wiki_page": {}})


def test_format_wiki_page_basic():
    data = {
        "wiki_page": {
            "title": "Installation",
            "version": 3,
            "author": {"name": "Alice"},
            "updated_on": "2025-06-15T10:00:00Z",
            "text": "h1. Installation Guide\n\nFollow these steps...",
        }
    }
    result = _format_wiki_page(data)
    assert "# Installation" in result
    assert "**Version:** 3" in result
    assert "**Author:** Alice" in result
    assert "Installation Guide" in result
    assert "Follow these steps" in result


def test_format_wiki_page_empty_content():
    data = {
        "wiki_page": {
            "title": "EmptyPage",
            "version": 1,
            "author": {"name": "Bob"},
            "updated_on": "2025-01-01",
            "text": "",
        }
    }
    result = _format_wiki_page(data)
    assert "_(empty page)_" in result


# --- custom fields ---


def _redmine_with_fields(fields: list[dict] | Exception) -> AsyncMock:
    redmine = AsyncMock()
    if isinstance(fields, Exception):
        redmine.get.side_effect = fields
    else:
        redmine.get.return_value = {"custom_fields": fields}
    return redmine


# _coerce_custom_value


def test_coerce_value_string_passthrough():
    assert _coerce_custom_value("High") == "High"


def test_coerce_value_int_becomes_string():
    assert _coerce_custom_value(3) == "3"


def test_coerce_value_bool_uses_redmine_encoding():
    """Redmine boolean custom fields want "1"/"0", not "true"/"false"."""
    assert _coerce_custom_value(True) == "1"
    assert _coerce_custom_value(False) == "0"


def test_coerce_value_none_becomes_empty_string():
    assert _coerce_custom_value(None) == ""


def test_coerce_value_list_for_multi_value_field():
    assert _coerce_custom_value(["iOS", "Android"]) == ["iOS", "Android"]


def test_coerce_value_list_of_bools():
    assert _coerce_custom_value([True, False]) == ["1", "0"]


# _build_custom_fields


@pytest.mark.asyncio
async def test_build_custom_fields_numeric_id_skips_lookup():
    """A numeric key needs no name resolution — and must not trigger an API call."""
    redmine = _redmine_with_fields([])
    result = await _build_custom_fields(redmine, "tok", {"5": "High"})

    assert result == [{"id": 5, "value": "High"}]
    redmine.get.assert_not_called()


@pytest.mark.asyncio
async def test_build_custom_fields_resolves_name_to_id():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    result = await _build_custom_fields(redmine, "tok", {"Severity": "High"})

    assert result == [{"id": 3, "value": "High"}]


@pytest.mark.asyncio
async def test_build_custom_fields_name_match_is_case_insensitive():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    result = await _build_custom_fields(redmine, "tok", {"severity": "High"})

    assert result == [{"id": 3, "value": "High"}]


@pytest.mark.asyncio
async def test_build_custom_fields_caches_the_name_map():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    await _build_custom_fields(redmine, "tok", {"Severity": "High"})
    await _build_custom_fields(redmine, "tok", {"Severity": "Low"})

    assert redmine.get.await_count == 1


@pytest.mark.asyncio
async def test_build_custom_fields_unknown_name_raises():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    with pytest.raises(CustomFieldError) as exc_info:
        await _build_custom_fields(redmine, "tok", {"Nonexistent": "x"})

    assert "Nonexistent" in str(exc_info.value)
    assert "no custom field with that name exists" in str(exc_info.value)


@pytest.mark.asyncio
async def test_build_custom_fields_without_admin_rights_says_to_use_ids():
    """/custom_fields.json is admin-only in Redmine; the error must be actionable."""
    redmine = _redmine_with_fields(RedmineForbiddenError(403, "Permission denied."))
    with pytest.raises(CustomFieldError) as exc_info:
        await _build_custom_fields(redmine, "tok", {"Severity": "High"})

    message = str(exc_info.value)
    assert "admin rights" in message
    assert "numeric field ID" in message


@pytest.mark.asyncio
async def test_build_custom_fields_ids_still_work_without_admin_rights():
    """A forbidden name lookup must not break callers who passed IDs."""
    redmine = _redmine_with_fields(RedmineForbiddenError(403, "Permission denied."))
    result = await _build_custom_fields(redmine, "tok", {"7": "2.4.1"})

    assert result == [{"id": 7, "value": "2.4.1"}]


@pytest.mark.asyncio
async def test_build_custom_fields_mixed_ids_and_names():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    result = await _build_custom_fields(
        redmine, "tok", {"Severity": "High", "7": ["a", "b"]}
    )

    assert {"id": 3, "value": "High"} in result
    assert {"id": 7, "value": ["a", "b"]} in result


@pytest.mark.asyncio
async def test_build_custom_fields_reports_every_unresolved_name():
    redmine = _redmine_with_fields([{"id": 3, "name": "Severity"}])
    with pytest.raises(CustomFieldError) as exc_info:
        await _build_custom_fields(redmine, "tok", {"Foo": "1", "Bar": "2"})

    message = str(exc_info.value)
    assert "Foo" in message and "Bar" in message
