"""
Integration: GET /graph/overview route against live Neo4j.

Tests use direct function call (driver injection pattern) rather than an HTTP client.
The devtools server module-level _driver is replaced with the test fixture driver.
"""

from __future__ import annotations

from conftest import TEST_DB, TEST_PROJECT_ID

import graphbase_memories.devtools.server as devtools_server

# ── helpers ───────────────────────────────────────────────────────────────────


async def _call(driver, **kwargs):
    """Inject driver and call graph_overview with given kwargs."""
    devtools_server._driver = driver
    from graphbase_memories.devtools.routes.graph import graph_overview

    return await graph_overview(**kwargs)


# ── tests ──────────────────────────────────────────────────────────────────────


async def test_empty_graph_returns_valid_structure(driver):
    """GET /graph/overview returns the expected top-level keys even on an empty graph."""
    result = await _call(driver)
    assert isinstance(result["nodes"], list)
    assert isinstance(result["edges"], list)
    assert "summary" in result
    assert "counts" in result["summary"]
    assert "edge_counts" in result["summary"]
    assert "total_nodes_in_graph" in result["summary"]
    assert "generated_at" in result["summary"]


async def test_project_without_workspace_has_no_member_of_edge(driver, fresh_project):
    """A Project node with no Workspace produces no MEMBER_OF edge in the response."""
    result = await _call(driver)

    node_ids = [n["id"] for n in result["nodes"]]
    assert TEST_PROJECT_ID in node_ids

    member_of_edges = [e for e in result["edges"] if e["type"] == "MEMBER_OF"]
    assert all(e["source"] != TEST_PROJECT_ID for e in member_of_edges)


async def test_project_with_workspace_has_member_of_edge(driver, fresh_workspace):
    """A Project linked to a Workspace produces a MEMBER_OF edge (source=project, target=ws)."""
    ws_id = fresh_workspace  # fixture yields the workspace id
    result = await _call(driver)

    node_ids = [n["id"] for n in result["nodes"]]
    assert TEST_PROJECT_ID in node_ids
    assert ws_id in node_ids

    member_of = [e for e in result["edges"] if e["type"] == "MEMBER_OF"]
    sources = {e["source"] for e in member_of}
    assert TEST_PROJECT_ID in sources


async def test_stale_project_flagged_in_response(driver, fresh_project):
    """A Project with last_seen 10 days ago is returned with is_stale=True."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (p:Project {id: $pid}) SET p.last_seen = datetime() - duration({days: 10})",
            pid=TEST_PROJECT_ID,
        )

    result = await _call(driver)
    test_node = next((n for n in result["nodes"] if n["id"] == TEST_PROJECT_ID), None)
    assert test_node is not None
    assert test_node["is_stale"] is True
    assert test_node["staleness_days"] is not None
    assert test_node["staleness_days"] > 7


async def test_max_nodes_cap_respected(driver, bulk_projects):
    """When more than max_nodes projects exist, returned nodes are capped."""
    result = await _call(driver, max_nodes=200)
    assert len(result["nodes"]) <= 200
    assert result["summary"]["capped_at"] == 200


async def test_cross_service_link_appears_in_edges(driver, fresh_project):
    """CROSS_SERVICE_LINK between two Projects appears in the edges list."""
    target_id = "test-graph-csl-target"
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MERGE (p2:Project {id: $p2id})
            ON CREATE SET p2.name = $p2id, p2.created_at = datetime()
            WITH p2
            MATCH (p1:Project {id: $p1id})
            MERGE (p1)-[:CROSS_SERVICE_LINK {type: "DEPENDS_ON"}]->(p2)
            """,
            p1id=TEST_PROJECT_ID,
            p2id=target_id,
        )
    try:
        result = await _call(driver)
        csl_edges = [e for e in result["edges"] if e["type"] == "CROSS_SERVICE_LINK"]
        assert len(csl_edges) >= 1
        sources = {e["source"] for e in csl_edges}
        assert TEST_PROJECT_ID in sources
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run(
                "MATCH (p:Project {id: $pid}) DETACH DELETE p",
                pid=target_id,
            )


async def test_summary_counts_include_all_labels(driver, fresh_project):
    """Summary counts dict contains all expected label keys."""
    result = await _call(driver)
    expected_labels = {"Project", "Workspace", "Session", "Decision",
                       "Pattern", "Context", "EntityFact", "ImpactEvent"}
    assert expected_labels.issubset(result["summary"]["counts"].keys())


async def test_include_stale_false_excludes_stale_projects(driver, fresh_project):
    """include_stale=False removes stale project nodes from the response."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (p:Project {id: $pid}) SET p.last_seen = datetime() - duration({days: 10})",
            pid=TEST_PROJECT_ID,
        )

    result = await _call(driver, include_stale=False)
    node_ids = [n["id"] for n in result["nodes"]]
    assert TEST_PROJECT_ID not in node_ids
