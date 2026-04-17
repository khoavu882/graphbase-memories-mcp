"""
Integration tests for the topology feature — T5.4.

Tests cover:
  - Scope validation (validate_workspace)
  - Node upserts (Service, DataSource, MessageQueue, Feature, BoundedContext)
  - Dual-label creation for Service nodes (:Project:Service)
  - Relationship creation and whitelist enforcement
  - Batch upsert with governance token
  - Traversal queries (get_service_dependencies, get_feature_workflow)

Each test manages its own node cleanup. IDs use a "topo-test-" prefix to
avoid collisions with other test suites.
"""

from __future__ import annotations

import uuid

from conftest import TEST_DB

# ── Helpers ───────────────────────────────────────────────────────────────────

WS_ID = "topo-test-workspace"
SVC_A = "topo-test-svc-a"
SVC_B = "topo-test-svc-b"
DS_ID = "topo-test-ds-1"
MQ_ID = "topo-test-mq-1"
FT_ID = "topo-test-feature-1"
BC_ID = "topo-test-bc-1"


async def _setup_workspace(driver):
    """Create a :Workspace node for tests that need workspace scope validation."""
    async with driver.session(database=TEST_DB) as s:
        await s.run(
            "MERGE (w:Workspace {id: $wid}) ON CREATE SET w.name = $wid, w.created_at = datetime()",
            wid=WS_ID,
        )


async def _cleanup(driver, node_ids=(), workspace_ids=()):
    """DETACH DELETE all nodes by id, including their relationships."""
    async with driver.session(database=TEST_DB) as s:
        for nid in node_ids:
            await s.run("MATCH (n {id: $id}) DETACH DELETE n", id=nid)
        for wid in workspace_ids:
            await s.run("MATCH (w:Workspace {id: $id}) DETACH DELETE w", id=wid)
        await s.run("MATCH (t:GovernanceToken) DETACH DELETE t")


# ── Scope validation ──────────────────────────────────────────────────────────


async def test_validate_workspace_resolved(driver):
    """validate_workspace returns ScopeState.resolved for an existing workspace."""
    from graphbase_memories.engines import scope as scope_engine
    from graphbase_memories.mcp.schemas.enums import ScopeState

    await _setup_workspace(driver)
    try:
        state = await scope_engine.validate_workspace(WS_ID, driver, TEST_DB)
        assert state == ScopeState.resolved
    finally:
        await _cleanup(driver, workspace_ids=[WS_ID])


async def test_validate_workspace_unresolved_for_missing(driver):
    """validate_workspace returns ScopeState.unresolved for a non-existent workspace."""
    from graphbase_memories.engines import scope as scope_engine
    from graphbase_memories.mcp.schemas.enums import ScopeState

    state = await scope_engine.validate_workspace("no-such-workspace-xyz", driver, TEST_DB)
    assert state == ScopeState.unresolved


async def test_validate_workspace_unresolved_for_none(driver):
    """validate_workspace returns ScopeState.unresolved when workspace_id is None."""
    from graphbase_memories.engines import scope as scope_engine
    from graphbase_memories.mcp.schemas.enums import ScopeState

    state = await scope_engine.validate_workspace(None, driver, TEST_DB)
    assert state == ScopeState.unresolved


# ── Service upsert ────────────────────────────────────────────────────────────


async def test_upsert_service_creates_dual_label_node(driver):
    """register_service must create a node carrying BOTH :Project and :Service labels."""
    from graphbase_memories.graph.repositories import topology_repo

    await _setup_workspace(driver)
    try:
        await topology_repo.upsert_service(
            driver,
            TEST_DB,
            service_id=SVC_A,
            name="Service A",
            workspace_id=WS_ID,
            service_type="api",
            health_status="healthy",
        )
        async with driver.session(database=TEST_DB) as s:
            result = await s.run("MATCH (n {id: $id}) RETURN labels(n) AS lbls", id=SVC_A)
            record = await result.single()
        assert record is not None, "Node not created"
        assert "Project" in record["lbls"], "Missing :Project label"
        assert "Service" in record["lbls"], "Missing :Service label"
    finally:
        await _cleanup(driver, [SVC_A], [WS_ID])


async def test_upsert_service_idempotent(driver):
    """Calling upsert_service twice returns the same service_id (MERGE semantics)."""
    from graphbase_memories.graph.repositories import topology_repo

    await _setup_workspace(driver)
    try:
        node1 = await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_A, name="Service A", workspace_id=WS_ID
        )
        node2 = await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_A, name="Service A updated", workspace_id=WS_ID
        )
        assert node1.id == node2.id
        # Second call updates the display_name
        assert node2.display_name == "Service A updated"
    finally:
        await _cleanup(driver, [SVC_A], [WS_ID])


async def test_register_service_engine_raises_for_missing_workspace(driver):
    """topology_write.register_service raises ValueError when workspace does not exist."""
    import pytest

    from graphbase_memories.engines import topology_write as eng
    from graphbase_memories.mcp.schemas.topology import RegisterServiceInput

    inp = RegisterServiceInput(
        service_id="topo-orphan-svc",
        name="Orphan",
        workspace_id="workspace-does-not-exist-xyz",
    )
    with pytest.raises(ValueError, match="not found"):
        await eng.register_service(inp, driver, TEST_DB)


# ── Infrastructure node upserts ───────────────────────────────────────────────


async def test_upsert_datasource(driver):
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        node = await topology_repo.upsert_datasource(
            driver,
            TEST_DB,
            source_id=DS_ID,
            source_type="postgresql",
            host="db.example.com",
            workspace_id=WS_ID,
        )
        assert node.id == DS_ID
        assert node.source_type == "postgresql"
        assert node.workspace_id == WS_ID
    finally:
        await _cleanup(driver, [DS_ID], [WS_ID])


async def test_upsert_message_queue(driver):
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        node = await topology_repo.upsert_message_queue(
            driver,
            TEST_DB,
            queue_id=MQ_ID,
            queue_type="kafka",
            topic_or_exchange="payments.events",
            workspace_id=WS_ID,
        )
        assert node.id == MQ_ID
        assert node.queue_type == "kafka"
        assert node.topic_or_exchange == "payments.events"
    finally:
        await _cleanup(driver, [MQ_ID], [WS_ID])


async def test_upsert_feature(driver):
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        node = await topology_repo.upsert_feature(
            driver,
            TEST_DB,
            feature_id=FT_ID,
            name="User Onboarding",
            workspace_id=WS_ID,
            workflow_order=1,
        )
        assert node.id == FT_ID
        assert node.name == "User Onboarding"
        assert node.workflow_order == 1
    finally:
        await _cleanup(driver, [FT_ID], [WS_ID])


async def test_upsert_bounded_context(driver):
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        node = await topology_repo.upsert_bounded_context(
            driver,
            TEST_DB,
            context_id=BC_ID,
            name="Payments",
            domain="Finance",
            workspace_id=WS_ID,
        )
        assert node.id == BC_ID
        assert node.name == "Payments"
        assert node.domain == "Finance"
    finally:
        await _cleanup(driver, [BC_ID], [WS_ID])


# ── Relationship creation ─────────────────────────────────────────────────────


async def test_link_topology_nodes_creates_edge(driver):
    """link_topology_nodes dispatches to link_service_dependency, creating a CALLS_DOWNSTREAM edge."""
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_A, name="A", workspace_id=WS_ID
        )
        await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_B, name="B", workspace_id=WS_ID
        )
        record = await topology_repo.link_topology_nodes(
            from_id=SVC_A, to_id=SVC_B, rel_type="CALLS_DOWNSTREAM",
            driver=driver, database=TEST_DB,
        )
        assert record["from_id"] == SVC_A
        assert record["to_id"] == SVC_B
        assert record["rel_type"] == "CALLS_DOWNSTREAM"
        assert record.get("status") != "node_not_found"
        assert record.get("status") != "invalid_rel_type"

        # Verify edge exists in graph
        async with driver.session(database=TEST_DB) as s:
            result = await s.run(
                "MATCH (a:Service {id: $a})-[r:CALLS_DOWNSTREAM]->(b:Service {id: $b}) RETURN r",
                a=SVC_A,
                b=SVC_B,
            )
            rec = await result.single()
        assert rec is not None, "CALLS_DOWNSTREAM edge not found in graph"
    finally:
        await _cleanup(driver, [SVC_A, SVC_B], [WS_ID])


async def test_link_topology_nodes_invalid_rel_type_returns_status(driver):
    """link_topology_nodes returns status='invalid_rel_type' for an incompatible rel_type."""
    await _setup_workspace(driver)
    from graphbase_memories.graph.repositories import topology_repo

    try:
        await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_A, name="A", workspace_id=WS_ID
        )
        await topology_repo.upsert_service(
            driver, TEST_DB, service_id=SVC_B, name="B", workspace_id=WS_ID
        )
        # READS_FROM is valid for Service→DataSource, not Service→Service
        record = await topology_repo.link_topology_nodes(
            from_id=SVC_A, to_id=SVC_B, rel_type="READS_FROM",
            driver=driver, database=TEST_DB,
        )
        assert record["status"] == "invalid_rel_type"
        assert "error" in record
        assert "CALLS_DOWNSTREAM" in record["error"] or "CALLS_UPSTREAM" in record["error"]
    finally:
        await _cleanup(driver, [SVC_A, SVC_B], [WS_ID])


# ── Batch upsert with governance token ────────────────────────────────────────


async def test_batch_upsert_shared_infrastructure(driver):
    """batch_upsert_shared_infrastructure creates nodes and consumes the token."""
    await _setup_workspace(driver)

    from graphbase_memories.engines import topology_write as eng
    from graphbase_memories.graph.repositories import token_repo
    from graphbase_memories.mcp.schemas.topology import (
        BatchUpsertInfraInput,
        DataSourceItem,
        MessageQueueItem,
    )

    token = await token_repo.create(
        content_preview="batch topology test",
        ttl_s=300,
        driver=driver,
        database=TEST_DB,
    )
    batch_ds = "topo-batch-ds-" + uuid.uuid4().hex[:6]
    batch_mq = "topo-batch-mq-" + uuid.uuid4().hex[:6]

    inp = BatchUpsertInfraInput(
        workspace_id=WS_ID,
        governance_token=token.id,
        nodes=[
            DataSourceItem(source_id=batch_ds, source_type="redis"),
            MessageQueueItem(queue_id=batch_mq, queue_type="kafka"),
        ],
    )
    try:
        result = await eng.batch_upsert_shared_infrastructure(inp, driver, TEST_DB)
        assert result.upserted == 2
        assert result.failed == 0

        # Token must be consumed — second call should raise
        import pytest

        inp2 = BatchUpsertInfraInput(
            workspace_id=WS_ID,
            governance_token=token.id,
            nodes=[DataSourceItem(source_id="topo-batch-ds-dup", source_type="redis")],
        )
        with pytest.raises(ValueError, match="invalid"):
            await eng.batch_upsert_shared_infrastructure(inp2, driver, TEST_DB)
    finally:
        await _cleanup(driver, [batch_ds, batch_mq, "topo-batch-ds-dup"], [WS_ID])


# ── Traversal ─────────────────────────────────────────────────────────────────


async def test_get_service_dependencies_downstream(driver):
    """get_service_dependencies returns downstream services in the correct direction."""
    await _setup_workspace(driver)
    from graphbase_memories.engines import topology_write as eng
    from graphbase_memories.mcp.schemas.topology import (
        GetServiceDependenciesInput,
        RegisterServiceInput,
    )

    svc_root = "topo-dep-root"
    svc_leaf = "topo-dep-leaf"
    try:
        await eng.register_service(
            RegisterServiceInput(service_id=svc_root, name="Root", workspace_id=WS_ID),
            driver,
            TEST_DB,
        )
        await eng.register_service(
            RegisterServiceInput(service_id=svc_leaf, name="Leaf", workspace_id=WS_ID),
            driver,
            TEST_DB,
        )
        from graphbase_memories.graph.repositories import topology_repo

        await topology_repo.link_topology_nodes(
            from_id=svc_root, to_id=svc_leaf, rel_type="CALLS_DOWNSTREAM",
            driver=driver, database=TEST_DB,
        )
        result = await eng.get_service_dependencies(
            GetServiceDependenciesInput(service_id=svc_root, direction="downstream", depth=2),
            driver,
            TEST_DB,
        )
        assert result.service_id == svc_root
        assert result.direction == "downstream"
        dep_ids = {d.service_id for d in result.dependencies}
        assert svc_leaf in dep_ids
    finally:
        await _cleanup(driver, [svc_root, svc_leaf], [WS_ID])
