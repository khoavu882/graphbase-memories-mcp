"""
Integration: GET /graph/overview route against live Neo4j.

Tests use direct function call (driver injection pattern) rather than an HTTP client.
"""

from __future__ import annotations

from conftest import TEST_DB, TEST_PROJECT_ID

# ── helpers ───────────────────────────────────────────────────────────────────


async def _call(driver, **kwargs):
    """Call graph_overview with driver and given kwargs."""
    from graphbase_memories.devtools.routes.graph import graph_overview

    return await graph_overview(driver, **kwargs)


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
    """When more than max_nodes projects exist, returned project nodes are capped.

    Workspace nodes are always returned unconditionally — they are structural
    root nodes, not counted against the cap. So total node count may exceed
    max_nodes by the number of Workspace nodes in the graph.
    """
    result = await _call(driver, max_nodes=200)
    project_nodes = [n for n in result["nodes"] if n["label"] == "Project"]
    assert len(project_nodes) <= 200
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
    expected_labels = {
        "Project",
        "Workspace",
        "Session",
        "Decision",
        "Pattern",
        "Context",
        "EntityFact",
        "ImpactEvent",
    }
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


async def test_topology_mode_includes_entity_fact_nodes(driver, fresh_workspace):
    """topology=True with workspace_id includes scoped EntityFact nodes and topology edges.

    Uses fresh_workspace fixture (which provides both a Project and a Workspace)
    so workspace_id filtering scopes results to only the test entities.
    """
    from conftest import TEST_PROJECT_ID

    svc_id = "test-topo-svc-001"
    bc_id = "test-topo-bc-001"
    ws_id = fresh_workspace  # e.g. "test-workspace-graph"
    async with driver.session(database=TEST_DB) as session:
        # Create two EntityFact nodes — both linked to the project (workspace-scoped),
        # with a BELONGS_TO entity-to-entity edge from svc to bc.
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            MERGE (svc:EntityFact {entity_name: $svc_name, scope: 'project'})
            ON CREATE SET svc.id = $svc_id, svc.fact = 'A test service', svc.created_at = datetime()
            SET svc.id = $svc_id
            MERGE (bc:EntityFact {entity_name: $bc_name, scope: 'project'})
            ON CREATE SET bc.id = $bc_id, bc.fact = 'A bounded context', bc.created_at = datetime()
            SET bc.id = $bc_id
            MERGE (svc)-[:BELONGS_TO]->(bc)
            MERGE (svc)-[:BELONGS_TO]->(p)
            MERGE (bc)-[:BELONGS_TO]->(p)
            """,
            svc_id=svc_id,
            svc_name="svc-test-topo",
            bc_id=bc_id,
            bc_name="bc-test-topo",
            pid=TEST_PROJECT_ID,
        )
    try:
        # Use workspace_id to scope results — avoids pollution from other test entities
        result = await _call(driver, topology=True, workspace_id=ws_id)
        entity_nodes = [n for n in result["nodes"] if n["label"] == "EntityFact"]
        assert len(entity_nodes) >= 1, "Expected EntityFact nodes in topology mode"

        # Verify category derivation from name prefix
        svc_nodes = [n for n in entity_nodes if n["display"] == "svc-test-topo"]
        assert svc_nodes, "Expected svc-test-topo entity node"
        assert svc_nodes[0]["category"] == "Service"

        # Verify BELONGS_TO edge between entities appears
        belongs_edges = [e for e in result["edges"] if e["type"] == "BELONGS_TO"]
        assert len(belongs_edges) >= 1, "Expected BELONGS_TO topology edges"

        # Verify topology_mode flag in summary
        assert result["summary"]["topology_mode"] is True
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run(
                "MATCH (e:EntityFact) WHERE e.id IN [$svc_id, $bc_id] DETACH DELETE e",
                svc_id=svc_id,
                bc_id=bc_id,
            )


async def test_topology_false_does_not_include_entity_nodes(driver, fresh_project):
    """topology=False (default) returns no EntityFact nodes in the nodes list."""
    result = await _call(driver, topology=False)
    entity_nodes = [n for n in result["nodes"] if n["label"] == "EntityFact"]
    assert len(entity_nodes) == 0, "EntityFact nodes should not appear in collapsed view"
