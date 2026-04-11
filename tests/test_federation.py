"""
Integration tests for FederationEngine.
Each test manages its own cleanup — no shared fixtures for workspace/service nodes.
"""

from __future__ import annotations

from conftest import TEST_DB


async def _cleanup(driver, service_ids=(), workspace_ids=()):
    async with driver.session(database=TEST_DB) as s:
        for sid in service_ids:
            # Delete all nodes that BELONGS_TO this project (DETACH cascades their edges, e.g. CSL)
            await s.run("MATCH (n)-[:BELONGS_TO]->(p:Project {id: $id}) DETACH DELETE n", id=sid)
            await s.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=sid)
        for wid in workspace_ids:
            await s.run("MATCH (w:Workspace {id: $id}) DETACH DELETE w", id=wid)


async def test_register_and_list(driver):
    from graphbase_memories.engines import federation as eng

    await eng.register_service("fed-svc-a", "fed-ws-1", "Service A", None, [], driver, TEST_DB)
    await eng.register_service("fed-svc-b", "fed-ws-1", "Service B", None, [], driver, TEST_DB)
    result = await eng.list_services("fed-ws-1", 60, driver, TEST_DB)

    assert result.workspace_id == "fed-ws-1"
    assert result.retrieval_status.value == "succeeded"
    ids = {s.service_id for s in result.services}
    assert "fed-svc-a" in ids
    assert "fed-svc-b" in ids

    await _cleanup(driver, ["fed-svc-a", "fed-svc-b"], ["fed-ws-1"])


async def test_deregister_removes_from_active_list(driver):
    from graphbase_memories.engines import federation as eng

    await eng.register_service("fed-svc-c", "fed-ws-2", None, None, [], driver, TEST_DB)
    await eng.deregister_service("fed-svc-c", driver, TEST_DB)

    result = await eng.list_services("fed-ws-2", 60, driver, TEST_DB)
    assert result.retrieval_status.value == "empty"
    assert result.services == []

    await _cleanup(driver, ["fed-svc-c"], ["fed-ws-2"])


async def test_workspace_created_false_on_second_register(driver):
    from graphbase_memories.engines import federation as eng

    r1 = await eng.register_service("fed-svc-d", "fed-ws-3", None, None, [], driver, TEST_DB)
    r2 = await eng.register_service("fed-svc-d", "fed-ws-3", None, None, [], driver, TEST_DB)

    assert r1.workspace_created is True
    assert r2.workspace_created is False

    await _cleanup(driver, ["fed-svc-d"], ["fed-ws-3"])


async def test_list_empty_workspace_returns_empty(driver):
    from graphbase_memories.engines import federation as eng

    result = await eng.list_services("nonexistent-ws-xyz", 60, driver, TEST_DB)
    assert result.retrieval_status.value == "empty"
    assert result.services == []
    assert result.workspace_id == "nonexistent-ws-xyz"


# ── Cross-service search (MS-B0) ──────────────────────────────────


async def test_search_cross_service_empty_query_returns_empty(driver):
    from graphbase_memories.engines import federation as eng

    result = await eng.search_cross_service(
        "xyzzy_nonexistent_term_12345",
        "nonexistent-ws-search",
        None,
        None,
        50,
        driver,
        TEST_DB,
    )
    assert result.retrieval_status.value == "empty"
    assert result.items == []
    assert result.total_count == 0


# ── Cross-service linking (MS-B1) ────────────────────────────────


async def test_link_cross_service_creates_edge(driver):
    from graphbase_memories.engines import federation as eng
    from graphbase_memories.graph.repositories import entity_repo

    # Pre-test cleanup to handle residual state from previous failed runs
    await _cleanup(driver, ["lnk-svc-a", "lnk-svc-b"], ["lnk-ws"])

    # Register two services in a workspace
    await eng.register_service("lnk-svc-a", "lnk-ws", None, None, [], driver, TEST_DB)
    await eng.register_service("lnk-svc-b", "lnk-ws", None, None, [], driver, TEST_DB)

    # Create one entity in each project
    e_a = await entity_repo.upsert(
        entity_name="AuthTokenA",
        fact="issues JWT",
        scope="project",
        project_id="lnk-svc-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="AuthTokenB",
        fact="validates JWT",
        scope="project",
        project_id="lnk-svc-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    result = await eng.create_cross_service_link(
        e_a.id, e_b.id, "DEPENDS_ON", "B depends on A's token format", 0.9, "test", driver, TEST_DB
    )
    assert result.status.value == "saved"

    # Verify edge exists
    async with driver.session(database=TEST_DB) as s:
        rec = await s.run(
            "MATCH (a)-[r:CROSS_SERVICE_LINK {type:'DEPENDS_ON'}]->(b) "
            "WHERE a.id=$aid AND b.id=$bid RETURN count(r) AS c",
            aid=e_a.id,
            bid=e_b.id,
        )
        row = await rec.single()
    assert row["c"] == 1

    # Post-test cleanup
    await _cleanup(driver, ["lnk-svc-a", "lnk-svc-b"], ["lnk-ws"])


async def test_link_same_project_rejected(driver, fresh_project):
    from graphbase_memories.engines import federation as eng
    from graphbase_memories.graph.repositories import entity_repo

    e1 = await entity_repo.upsert(
        entity_name="SameProj1",
        fact="fact1",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e2 = await entity_repo.upsert(
        entity_name="SameProj2",
        fact="fact2",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    result = await eng.create_cross_service_link(
        e1.id, e2.id, "DEPENDS_ON", "same project", 1.0, None, driver, TEST_DB
    )
    assert result.status.value == "failed"
    assert "same-project" in (result.message or "")


async def test_link_invalid_type_rejected(driver, fresh_project):
    import pytest

    from graphbase_memories.engines import federation as eng

    with pytest.raises(ValueError, match="Invalid link_type"):
        await eng.create_cross_service_link(
            "any-id", "other-id", "INVALID_TYPE", "x", 1.0, None, driver, TEST_DB
        )


async def test_link_duplicate_returns_skip(driver):
    from graphbase_memories.engines import federation as eng
    from graphbase_memories.graph.repositories import entity_repo

    # Pre-test cleanup to handle residual state from previous failed runs
    await _cleanup(driver, ["dup-svc-a", "dup-svc-b"], ["dup-ws"])

    await eng.register_service("dup-svc-a", "dup-ws", None, None, [], driver, TEST_DB)
    await eng.register_service("dup-svc-b", "dup-ws", None, None, [], driver, TEST_DB)

    e_a = await entity_repo.upsert(
        entity_name="DupA",
        fact="fa",
        scope="project",
        project_id="dup-svc-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="DupB",
        fact="fb",
        scope="project",
        project_id="dup-svc-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    r1 = await eng.create_cross_service_link(
        e_a.id, e_b.id, "SHARES_CONCEPT", "shared concept", 0.8, None, driver, TEST_DB
    )
    r2 = await eng.create_cross_service_link(
        e_a.id, e_b.id, "SHARES_CONCEPT", "shared concept", 0.8, None, driver, TEST_DB
    )
    assert r1.status.value == "saved"
    assert r2.status.value == "duplicate_skip"

    await _cleanup(driver, ["dup-svc-a", "dup-svc-b"], ["dup-ws"])
