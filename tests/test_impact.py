"""
Integration tests for ImpactEngine + impact_repo.
Tests use unique entity/project IDs and perform pre+post cleanup.
"""

from __future__ import annotations

from conftest import TEST_DB


async def _cleanup(driver, service_ids=(), workspace_ids=()):
    async with driver.session(database=TEST_DB) as s:
        for sid in service_ids:
            await s.run("MATCH (n)-[:BELONGS_TO]->(p:Project {id: $id}) DETACH DELETE n", id=sid)
            await s.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=sid)
        for wid in workspace_ids:
            await s.run("MATCH (w:Workspace {id: $id}) DETACH DELETE w", id=wid)
        # ImpactEvent nodes created by tests
        await s.run(
            "MATCH (ie:ImpactEvent) WHERE ie.source_project_id IN $ids DETACH DELETE ie",
            ids=list(service_ids),
        )


# ── MS-C0a: fetch_batch_neighbors ────────────────────────────────


async def test_batch_neighbors_empty_input(driver):
    from graphbase_memories.graph.repositories import impact_repo

    result = await impact_repo.fetch_batch_neighbors([], driver=driver, database=TEST_DB)
    assert result == []


async def test_batch_neighbors_returns_correct_project(driver):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.graph.repositories import entity_repo, impact_repo

    await _cleanup(driver, ["imp-svc-bn-a", "imp-svc-bn-b"], ["imp-ws-bn"])
    await fed.register_service("imp-svc-bn-a", "imp-ws-bn", None, None, [], driver, TEST_DB)
    await fed.register_service("imp-svc-bn-b", "imp-ws-bn", None, None, [], driver, TEST_DB)

    e_a = await entity_repo.upsert(
        entity_name="BnEntityA",
        fact="fa",
        scope="project",
        project_id="imp-svc-bn-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="BnEntityB",
        fact="fb",
        scope="project",
        project_id="imp-svc-bn-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    await fed.create_cross_service_link(
        e_a.id, e_b.id, "DEPENDS_ON", "b depends on a", 1.0, None, driver, TEST_DB
    )

    neighbors = await impact_repo.fetch_batch_neighbors([e_a.id], driver=driver, database=TEST_DB)
    assert len(neighbors) == 1
    assert neighbors[0].id == e_b.id
    assert neighbors[0].project_id == "imp-svc-bn-b"
    assert neighbors[0].edge_type == "DEPENDS_ON"

    await _cleanup(driver, ["imp-svc-bn-a", "imp-svc-bn-b"], ["imp-ws-bn"])


# ── MS-C0b: propagate_impact ──────────────────────────────────────


async def test_propagate_impact_no_links(driver, fresh_project):
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    e = await entity_repo.upsert(
        entity_name="IsolatedEntity",
        fact="no links",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    report = await eng.propagate_impact(e.id, "changed", "breaking", 3, driver, TEST_DB)

    assert report.affected_services == []
    assert report.overall_risk == "LOW"
    assert report.impact_event_id  # persisted

    # ImpactEvent should exist
    async with driver.session(database=TEST_DB) as s:
        res = await s.run("MATCH (ie:ImpactEvent {id: $id}) RETURN ie", id=report.impact_event_id)
        rec = await res.single()
    assert rec is not None


async def test_propagate_impact_depth1(driver):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    await _cleanup(driver, ["imp-d1-a", "imp-d1-b"], ["imp-ws-d1"])
    await fed.register_service("imp-d1-a", "imp-ws-d1", None, None, [], driver, TEST_DB)
    await fed.register_service("imp-d1-b", "imp-ws-d1", None, None, [], driver, TEST_DB)

    e_a = await entity_repo.upsert(
        entity_name="D1EntityA",
        fact="fa",
        scope="project",
        project_id="imp-d1-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="D1EntityB",
        fact="fb",
        scope="project",
        project_id="imp-d1-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    await fed.create_cross_service_link(
        e_a.id, e_b.id, "DEPENDS_ON", "test", 1.0, None, driver, TEST_DB
    )

    report = await eng.propagate_impact(e_a.id, "changed", "breaking", 3, driver, TEST_DB)

    assert len(report.affected_services) == 1
    svc = report.affected_services[0]
    assert svc.project_id == "imp-d1-b"
    assert svc.depth == 1
    assert svc.risk_level == "HIGH"
    assert report.overall_risk == "HIGH"

    await _cleanup(driver, ["imp-d1-a", "imp-d1-b"], ["imp-ws-d1"])


async def test_propagate_impact_depth2(driver):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    await _cleanup(driver, ["imp-d2-a", "imp-d2-b", "imp-d2-c"], ["imp-ws-d2"])
    for sid in ["imp-d2-a", "imp-d2-b", "imp-d2-c"]:
        await fed.register_service(sid, "imp-ws-d2", None, None, [], driver, TEST_DB)

    e_a = await entity_repo.upsert(
        entity_name="D2EntityA",
        fact="fa",
        scope="project",
        project_id="imp-d2-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="D2EntityB",
        fact="fb",
        scope="project",
        project_id="imp-d2-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_c = await entity_repo.upsert(
        entity_name="D2EntityC",
        fact="fc",
        scope="project",
        project_id="imp-d2-c",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    await fed.create_cross_service_link(
        e_a.id, e_b.id, "DEPENDS_ON", "a->b", 1.0, None, driver, TEST_DB
    )
    await fed.create_cross_service_link(
        e_b.id, e_c.id, "DEPENDS_ON", "b->c", 1.0, None, driver, TEST_DB
    )

    report = await eng.propagate_impact(e_a.id, "changed", "breaking", 3, driver, TEST_DB)

    by_project = {s.project_id: s for s in report.affected_services}
    assert "imp-d2-b" in by_project
    assert "imp-d2-c" in by_project
    assert by_project["imp-d2-b"].depth == 1
    assert by_project["imp-d2-b"].risk_level == "HIGH"
    assert by_project["imp-d2-c"].depth == 2
    assert by_project["imp-d2-c"].risk_level == "MEDIUM"

    await _cleanup(driver, ["imp-d2-a", "imp-d2-b", "imp-d2-c"], ["imp-ws-d2"])


async def test_propagate_impact_contradicts_elevates_to_critical(driver):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    await _cleanup(driver, ["imp-crit-a", "imp-crit-b"], ["imp-ws-crit"])
    await fed.register_service("imp-crit-a", "imp-ws-crit", None, None, [], driver, TEST_DB)
    await fed.register_service("imp-crit-b", "imp-ws-crit", None, None, [], driver, TEST_DB)

    e_a = await entity_repo.upsert(
        entity_name="CritEntityA",
        fact="fa",
        scope="project",
        project_id="imp-crit-a",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_b = await entity_repo.upsert(
        entity_name="CritEntityB",
        fact="fb",
        scope="project",
        project_id="imp-crit-b",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    await fed.create_cross_service_link(
        e_a.id, e_b.id, "CONTRADICTS", "conflict", 0.9, None, driver, TEST_DB
    )

    report = await eng.propagate_impact(e_a.id, "changed", "breaking", 3, driver, TEST_DB)

    assert report.overall_risk == "CRITICAL"
    assert report.affected_services[0].risk_level == "CRITICAL"

    await _cleanup(driver, ["imp-crit-a", "imp-crit-b"], ["imp-ws-crit"])


async def test_impact_event_persisted(driver, fresh_project):
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    e = await entity_repo.upsert(
        entity_name="PersistEntity",
        fact="fp",
        scope="project",
        project_id=fresh_project,
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    report = await eng.propagate_impact(e.id, "test persist", "info", 1, driver, TEST_DB)

    async with driver.session(database=TEST_DB) as s:
        res = await s.run(
            "MATCH (ie:ImpactEvent {id: $id}) RETURN ie.source_entity_id AS sid",
            id=report.impact_event_id,
        )
        rec = await res.single()
    assert rec is not None
    assert rec["sid"] == e.id


# ── MS-C1: graph_health + detect_conflicts ────────────────────────


async def test_graph_health_empty_workspace(driver):
    from graphbase_memories.engines import impact as eng

    report = await eng.graph_health("nonexistent-health-ws", driver, TEST_DB)
    assert report.service_count == 0
    assert report.services == []
    assert report.total_conflicts == 0


async def test_graph_health_returns_correct_counts(driver, fresh_project):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    await _cleanup(driver, ["health-svc"], ["health-ws"])
    await fed.register_service("health-svc", "health-ws", None, None, [], driver, TEST_DB)

    for i in range(3):
        await entity_repo.upsert(
            entity_name=f"HealthEntity{i}",
            fact=f"f{i}",
            scope="project",
            project_id="health-svc",
            focus=None,
            driver=driver,
            database=TEST_DB,
        )

    report = await eng.graph_health("health-ws", driver, TEST_DB)

    svc = next((s for s in report.services if s.service_id == "health-svc"), None)
    assert svc is not None
    assert svc.entity_count == 3

    await _cleanup(driver, ["health-svc"], ["health-ws"])


async def test_detect_conflicts_empty_when_none(driver):
    from graphbase_memories.engines import impact as eng

    conflicts = await eng.detect_conflicts("nonexistent-conflict-ws", 100, driver, TEST_DB)
    assert conflicts == []


async def test_detect_conflicts_returns_contradicts_only(driver):
    from graphbase_memories.engines import federation as fed
    from graphbase_memories.engines import impact as eng
    from graphbase_memories.graph.repositories import entity_repo

    await _cleanup(driver, ["conf-svc-x", "conf-svc-y"], ["conf-ws"])
    await fed.register_service("conf-svc-x", "conf-ws", None, None, [], driver, TEST_DB)
    await fed.register_service("conf-svc-y", "conf-ws", None, None, [], driver, TEST_DB)

    e_x = await entity_repo.upsert(
        entity_name="ConflEntityX",
        fact="fx",
        scope="project",
        project_id="conf-svc-x",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )
    e_y = await entity_repo.upsert(
        entity_name="ConflEntityY",
        fact="fy",
        scope="project",
        project_id="conf-svc-y",
        focus=None,
        driver=driver,
        database=TEST_DB,
    )

    await fed.create_cross_service_link(
        e_x.id, e_y.id, "DEPENDS_ON", "dep", 1.0, None, driver, TEST_DB
    )
    await fed.create_cross_service_link(
        e_x.id, e_y.id, "CONTRADICTS", "conflict", 0.8, None, driver, TEST_DB
    )

    conflicts = await eng.detect_conflicts("conf-ws", 100, driver, TEST_DB)
    # Only CONTRADICTS should appear
    assert len(conflicts) == 1
    assert conflicts[0].source_project == "conf-svc-x"
    assert conflicts[0].target_project == "conf-svc-y"

    await _cleanup(driver, ["conf-svc-x", "conf-svc-y"], ["conf-ws"])
