"""
Integration: devtools graph stats and memory search routes against live Neo4j.
"""

from __future__ import annotations

from conftest import TEST_DB, TEST_PROJECT_ID  # noqa: F401

import graphbase_memories.devtools.server as devtools_server


async def test_graph_stats_returns_node_counts(driver):
    """GET /graph/stats returns node_counts dict with known labels."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats()

    assert "node_counts" in result
    assert "relationship_counts" in result
    assert "checked_at" in result

    expected_labels = {"Project", "Session", "Decision", "Pattern", "Context", "EntityFact"}
    for label in expected_labels:
        assert label in result["node_counts"], f"Missing label: {label}"


async def test_graph_stats_counts_are_non_negative(driver):
    """All node and relationship counts are non-negative integers."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats()

    for label, cnt in result["node_counts"].items():
        assert isinstance(cnt, int) and cnt >= 0, f"{label} count invalid: {cnt}"

    for rtype, cnt in result["relationship_counts"].items():
        assert isinstance(cnt, int) and cnt >= 0, f"{rtype} count invalid: {cnt}"


async def test_graph_stats_project_count_increases(driver, fresh_project):
    """After creating a project, Project count is at least 1."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats()
    assert result["node_counts"]["Project"] >= 1


async def test_memory_search_returns_list(driver):
    """POST /memory/search with a query returns a list."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.memory import MemorySearchRequest, search_memory

    body = MemorySearchRequest(query="test", limit=10)
    result = await search_memory(body)

    assert isinstance(result, list)


async def test_memory_search_with_label_filter(driver, fresh_project):
    """POST /memory/search with label=Session filters correctly."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.memory import MemorySearchRequest, search_memory

    # Create a session node to search for
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            CREATE (s:Session {
                id: 'test-search-session-001',
                title: 'searchable test session',
                summary: 'unique search phrase xqzwk',
                created_at: datetime()
            })
            """,
        )

    try:
        body = MemorySearchRequest(query="unique search phrase xqzwk", label="Session", limit=5)
        result = await search_memory(body)
        assert isinstance(result, list)
        # If found, verify it's a Session
        if result:
            assert all(r.get("_label") == "Session" for r in result)
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run(
                "MATCH (s:Session {id: 'test-search-session-001'}) DETACH DELETE s"
            )


async def test_memory_list_returns_nodes(driver, fresh_project):
    """GET /memory returns a list of memory nodes."""
    devtools_server._driver = driver

    from graphbase_memories.devtools.routes.memory import list_memory

    result = await list_memory(project_id=None, label=None, limit=10)
    assert isinstance(result, list)


async def test_memory_node_not_found_raises_404(driver):
    """GET /memory/{node_id} for a nonexistent ID raises 404."""
    devtools_server._driver = driver

    from fastapi import HTTPException

    from graphbase_memories.devtools.routes.memory import get_node

    try:
        await get_node("nonexistent-node-id-zzzz")
        raise AssertionError("Should have raised HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 404
