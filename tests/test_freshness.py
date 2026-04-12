"""Tests for freshness engine + retrieval annotation (Phase 2-F)."""

from __future__ import annotations

from datetime import date

from conftest import TEST_DB


async def test_freshness_empty_project(driver, fresh_project):
    """Fresh project with no old nodes reports stale_count=0."""
    from graphbase_memories.engines.freshness import scan

    report = await scan(
        project_id=fresh_project,
        stale_after_days=30,
        scan_limit=50,
        driver=driver,
        database=TEST_DB,
    )
    assert report.stale_count == 0
    assert report.stale_items == []
    assert report.checked_at is not None


async def test_freshness_finds_old_decision(driver, fresh_project):
    """Decision with updated_at set 60 days ago appears in stale_items."""
    from graphbase_memories.engines.freshness import scan
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import FreshnessLevel, MemoryScope

    decision = DecisionSchema(
        title="Legacy auth token approach",
        rationale="was chosen before security audit",
        owner="platform",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.7,
    )
    result = await save_decision(decision, fresh_project, None, None, driver, TEST_DB)
    node_id = result.artifact_id

    # Manually backdate the decision to 60 days ago
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (d:Decision {id: $id})
            SET d.updated_at = datetime() - duration('P60D'),
                d.created_at = datetime() - duration('P60D')
            """,
            id=node_id,
        )

    report = await scan(
        project_id=fresh_project,
        stale_after_days=30,
        scan_limit=50,
        driver=driver,
        database=TEST_DB,
    )
    stale_ids = {item.node_id for item in report.stale_items}
    assert node_id in stale_ids, "Backdated decision must appear in stale_items"

    stale_entry = next(i for i in report.stale_items if i.node_id == node_id)
    assert stale_entry.freshness == FreshnessLevel.stale
    assert stale_entry.age_days >= 59
    assert report.stale_count >= 1
    assert report.next_step is not None


async def test_retrieval_annotates_freshness(driver, fresh_project):
    """retrieve_context items carry _freshness annotation after Phase 2-F."""
    from graphbase_memories.engines.retrieval import execute
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, RetrievalStatus

    decision = DecisionSchema(
        title="Use circuit breaker for downstream calls",
        rationale="prevents cascade failures",
        owner="arch",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.9,
    )
    await save_decision(decision, fresh_project, None, None, driver, TEST_DB)

    bundle = await execute(
        project_id=fresh_project,
        scope="project",
        focus=None,
        categories=None,
        topic=None,
        driver=driver,
        database=TEST_DB,
    )
    assert bundle.retrieval_status == RetrievalStatus.succeeded
    assert len(bundle.items) >= 1
    freshness_values = {"current", "recent", "stale"}
    for item in bundle.items:
        assert "_freshness" in item, f"Item missing _freshness: {item.get('title')}"
        assert item["_freshness"] in freshness_values
