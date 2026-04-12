"""Tests for MCP resources layer (Phase 3-C)."""

from __future__ import annotations

from types import SimpleNamespace

from conftest import TEST_DB


async def test_schema_resource_returns_yaml():
    """schema_resource returns static YAML — no driver needed."""
    from graphbase_memories.mcp.resources import schema_resource

    result = await schema_resource()
    assert isinstance(result, str)
    assert "node_labels:" in result
    assert "relationships:" in result
    assert "Decision" in result
    assert "BELONGS_TO" in result


async def test_services_resource_empty(driver):
    """services_resource returns empty marker when no services are registered."""
    from graphbase_memories.mcp.resources import services_resource

    ctx = SimpleNamespace(lifespan_context={"driver": driver})
    result = await services_resource(ctx)
    assert isinstance(result, str)
    assert "services:" in result


async def test_services_resource_with_data(driver):
    """services_resource lists registered services after register_service()."""
    from graphbase_memories.engines.federation import register_service
    from graphbase_memories.mcp.resources import services_resource

    await register_service(
        "svc-test-resource",
        "wks-resource-test",
        "Resource Test Service",
        None,
        [],
        driver,
        TEST_DB,
    )

    ctx = SimpleNamespace(lifespan_context={"driver": driver})
    result = await services_resource(ctx)
    assert "svc-test-resource" in result

    # Cleanup
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (s:Service {service_id: $sid}) DETACH DELETE s",
            sid="svc-test-resource",
        )
        await session.run(
            "MATCH (w:Workspace {id: $wid}) DETACH DELETE w",
            wid="wks-resource-test",
        )


async def test_session_resource_not_found(driver):
    """session_resource returns error string for unknown session_id."""
    from graphbase_memories.mcp.resources import session_resource

    ctx = SimpleNamespace(lifespan_context={"driver": driver})
    result = await session_resource(ctx, "nonexistent-session-phase3c")
    assert "error:" in result
    assert "nonexistent-session-phase3c" in result
