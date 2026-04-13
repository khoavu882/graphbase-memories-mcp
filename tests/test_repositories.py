"""
Integration: CRUD operations for each repository.
Each test is independent — uses fresh_project fixture.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from conftest import TEST_DB
import pytest

# ── Session repo ────────────────────────────────────────────────


async def test_session_create(driver, fresh_project):
    from graphbase_memories.graph.repositories import session_repo

    node = await session_repo.create(
        objective="Implement auth module",
        actions_taken=["wrote tests", "reviewed PR"],
        decisions_made=["use JWT"],
        open_items=["deploy"],
        next_actions=["tag release"],
        save_scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    assert node.id
    assert node.status == "saved"
    assert isinstance(node.created_at, datetime)
    assert node.created_at.tzinfo is not None, "created_at must be timezone-aware"


async def test_session_link_produced(driver, fresh_project):
    from graphbase_memories.graph.repositories import decision_repo, session_repo

    session_node = await session_repo.create(
        objective="link test",
        actions_taken=[],
        decisions_made=[],
        open_items=[],
        next_actions=[],
        save_scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    decision_node = await decision_repo.create(
        title="Use Redis for caching",
        rationale="low latency needs",
        owner="team",
        date=date.today().isoformat(),
        scope="project",
        confidence=0.9,
        project_id=fresh_project,
        focus=None,
        dedup_status="new",
        driver=driver,
        database=TEST_DB,
    )
    # Must not raise
    await session_repo.link_produced(session_node.id, decision_node.id, driver, TEST_DB)

    async with driver.session(database=TEST_DB) as s:
        result = await s.run(
            "MATCH (s:Session {id: $sid})-[:PRODUCED]->(d:Decision {id: $did}) RETURN count(*) AS c",
            sid=session_node.id,
            did=decision_node.id,
        )
        record = await result.single()
    assert record["c"] == 1, ":PRODUCED relationship not created"


# ── Decision repo ────────────────────────────────────────────────


async def test_decision_create_and_hash(driver, fresh_project):
    from graphbase_memories.graph.repositories import decision_repo

    node = await decision_repo.create(
        title="Use PostgreSQL",
        rationale="ACID compliance required",
        owner="alice",
        date=date.today().isoformat(),
        scope="project",
        confidence=0.95,
        project_id=fresh_project,
        focus=None,
        dedup_status="new",
        driver=driver,
        database=TEST_DB,
    )
    assert node.id
    assert node.content_hash
    assert len(node.content_hash) == 64  # SHA-256 hex

    found = await decision_repo.find_by_hash(node.content_hash, "project", driver, TEST_DB)
    assert found is not None
    assert found["id"] == node.id


async def test_decision_add_supersedes(driver, fresh_project):
    from graphbase_memories.graph.repositories import decision_repo

    older = await decision_repo.create(
        title="Use MySQL",
        rationale="familiar tech",
        owner="bob",
        date=date.today().isoformat(),
        scope="project",
        confidence=0.6,
        project_id=fresh_project,
        focus=None,
        dedup_status="new",
        driver=driver,
        database=TEST_DB,
    )
    newer = await decision_repo.create(
        title="Use PostgreSQL v2",
        rationale="better JSON support",
        owner="bob",
        date=date.today().isoformat(),
        scope="project",
        confidence=0.9,
        project_id=fresh_project,
        focus=None,
        dedup_status="supersede",
        driver=driver,
        database=TEST_DB,
    )
    await decision_repo.add_supersedes(newer.id, older.id, driver, TEST_DB)

    async with driver.session(database=TEST_DB) as s:
        result = await s.run(
            "MATCH (n:Decision {id: $nid})-[:SUPERSEDES]->(o:Decision {id: $oid}) RETURN count(*) AS c",
            nid=newer.id,
            oid=older.id,
        )
        rec = await result.single()
    assert rec["c"] == 1


# ── Pattern repo ────────────────────────────────────────────────


async def test_pattern_create_and_dedup_hash(driver, fresh_project):
    from graphbase_memories.graph.repositories import pattern_repo

    node = await pattern_repo.create(
        trigger="Before merging a PR",
        repeatable_steps=["run lint", "run tests", "review diff"],
        exclusions=["hotfix branches"],
        scope="project",
        last_validated_at=datetime.now(UTC).isoformat(),
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    assert node.id
    assert node.content_hash

    found = await pattern_repo.find_by_hash(node.content_hash, "project", driver, TEST_DB)
    assert found is not None
    assert found["id"] == node.id


# ── Context repo ────────────────────────────────────────────────


async def test_context_create(driver, fresh_project):
    from graphbase_memories.graph.repositories import context_repo

    node = await context_repo.create(
        content="The service is deployed on Kubernetes with 3 replicas",
        topic="deployment",
        scope="project",
        relevance_score=0.85,
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    assert node.id
    assert node.relevance_score == pytest.approx(0.85)
    assert node.created_at.tzinfo is not None


# ── Entity repo ────────────────────────────────────────────────


async def test_entity_upsert_idempotent(driver, fresh_project):
    from graphbase_memories.graph.repositories import entity_repo

    node1 = await entity_repo.upsert(
        entity_name="AuthService",
        fact="handles JWT token issuance and validation",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    # Upsert again — same entity_name+scope should return same id
    node2 = await entity_repo.upsert(
        entity_name="AuthService",
        fact="updated: also handles refresh tokens",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    assert node1.id == node2.id, "Upsert must return the same node id for same entity_name+scope"


# ── Token repo ────────────────────────────────────────────────


async def test_governance_token_create_and_consume(driver):
    from graphbase_memories.graph.repositories import token_repo

    token = await token_repo.create(
        content_preview="Deploy auth service to production",
        ttl_s=300,
        driver=driver,
        database=TEST_DB,
    )
    assert token.id
    assert token.expires_at > datetime.now(UTC)

    # First consumption: valid
    valid = await token_repo.validate_and_consume(token.id, driver, TEST_DB)
    assert valid is True

    # Second consumption: already used
    reused = await token_repo.validate_and_consume(token.id, driver, TEST_DB)
    assert reused is False


# ── Federation repos ─────────────────────────────────────────────


async def test_register_service_creates_workspace(driver, clean_federation):
    from graphbase_memories.graph.repositories import federation_repo

    project, workspace, created = await federation_repo.register_service(
        service_id="test-svc-a",
        workspace_id="test-ws",
        display_name="Test A",
        description=None,
        tags=[],
        driver=driver,
        database=TEST_DB,
    )
    assert workspace.id == "test-ws"
    assert created is True
    assert project.status == "active"
    assert project.workspace_id == "test-ws"


async def test_register_service_idempotent(driver, clean_federation):
    from graphbase_memories.graph.repositories import federation_repo

    _, _, created_first = await federation_repo.register_service(
        service_id="test-svc-b",
        workspace_id="test-ws-idem",
        display_name="Test B",
        description=None,
        tags=[],
        driver=driver,
        database=TEST_DB,
    )
    _, _, created_second = await federation_repo.register_service(
        service_id="test-svc-b",
        workspace_id="test-ws-idem",
        display_name="Test B",
        description=None,
        tags=[],
        driver=driver,
        database=TEST_DB,
    )
    assert created_first is True
    assert created_second is False


async def test_workspace_id_normalized_lowercase(driver, clean_federation):
    from graphbase_memories.graph.repositories import federation_repo

    project, workspace, _ = await federation_repo.register_service(
        service_id="test-svc-c",
        workspace_id="UPPER-CASE",
        display_name="Test C",
        description=None,
        tags=[],
        driver=driver,
        database=TEST_DB,
    )
    assert workspace.id == "upper-case"
    assert project.workspace_id == "upper-case"


async def test_fetch_batch_neighbors_empty_input(driver):
    from graphbase_memories.graph.repositories import impact_repo

    result = await impact_repo.fetch_batch_neighbors([], driver=driver, database=TEST_DB)
    assert result == []
