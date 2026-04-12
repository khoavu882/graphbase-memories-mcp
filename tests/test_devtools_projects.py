"""
Integration: devtools project registry and hygiene control routes against live Neo4j.
"""

from __future__ import annotations

from conftest import TEST_PROJECT_ID

import graphbase_memories.devtools.server as devtools_server

# ── Projects ─────────────────────────────────────────────────────────────────


async def test_list_projects_returns_list(driver):
    """GET /projects returns a list."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.projects import list_projects

    result = await list_projects()
    assert isinstance(result, list)


async def test_list_projects_includes_test_project(driver, fresh_project):
    """GET /projects includes the freshly created test project."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.projects import list_projects

    result = await list_projects()
    ids = [p["id"] for p in result]
    assert TEST_PROJECT_ID in ids


async def test_project_includes_node_counts(driver, fresh_project):
    """Project entries include node_counts dict."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.projects import list_projects

    result = await list_projects()
    test_proj = next((p for p in result if p["id"] == TEST_PROJECT_ID), None)
    assert test_proj is not None
    assert "node_counts" in test_proj
    assert "staleness_days" in test_proj


async def test_project_node_counts_are_integers(driver, fresh_project):
    """Node counts in project entries are non-negative integers."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.projects import list_projects

    result = await list_projects()
    test_proj = next((p for p in result if p["id"] == TEST_PROJECT_ID), None)
    assert test_proj is not None

    for label, cnt in test_proj["node_counts"].items():
        assert isinstance(cnt, int) and cnt >= 0, f"{label}: {cnt}"


async def test_get_single_project(driver, fresh_project):
    """GET /projects/{project_id} returns the project."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.projects import get_project

    result = await get_project(TEST_PROJECT_ID)
    assert result["id"] == TEST_PROJECT_ID


async def test_get_project_not_found_raises_404(driver):
    """GET /projects/{project_id} for unknown project raises 404."""
    devtools_server._driver = driver

    from fastapi import HTTPException

    from graphbase_memories.devtools.routes.projects import get_project

    try:
        await get_project("nonexistent-project-id-zzzz")
        raise AssertionError("Should have raised HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 404


# ── Hygiene ───────────────────────────────────────────────────────────────────


async def test_hygiene_status_returns_structure(driver):
    """GET /hygiene/status returns projects list and pending_saves_total."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.hygiene import hygiene_status

    result = await hygiene_status()

    assert "projects" in result
    assert "pending_saves_total" in result
    assert "checked_at" in result
    assert isinstance(result["projects"], list)
    assert isinstance(result["pending_saves_total"], int)


async def test_hygiene_status_project_entry_structure(driver, fresh_project):
    """Each project entry in hygiene status has expected fields."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.hygiene import hygiene_status

    result = await hygiene_status()
    test_proj = next((p for p in result["projects"] if p["project_id"] == TEST_PROJECT_ID), None)
    assert test_proj is not None
    assert "last_hygiene_at" in test_proj
    assert "days_since" in test_proj
    assert "needs_hygiene" in test_proj


async def test_hygiene_run_returns_report(driver, fresh_project):
    """POST /hygiene/run returns a hygiene report."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.hygiene import HygieneRunRequest, run_hygiene

    body = HygieneRunRequest(project_id=TEST_PROJECT_ID, scope="project")
    result = await run_hygiene(body)

    # Result is a model_dump() dict from HygieneReport
    assert isinstance(result, dict)


async def test_hygiene_run_global_scope(driver):
    """POST /hygiene/run with scope=global runs without error."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.hygiene import HygieneRunRequest, run_hygiene

    body = HygieneRunRequest(project_id=None, scope="global")
    result = await run_hygiene(body)

    assert isinstance(result, dict)
