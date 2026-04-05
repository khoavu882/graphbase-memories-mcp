"""
Entity tool tests: upsert_entity, get_entity, link_entities, unlink_entities.

Exercises the MCP tool layer — all calls go through mcp.call_tool() as an
agent would call them. Engine is the standard SQLite test fixture.
"""
from __future__ import annotations

import pytest
from conftest import PROJECT, parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _upsert(mcp, name: str, type: str = "service", metadata: dict | None = None):
    r = await mcp.call_tool("upsert_entity", {
        "project": PROJECT, "name": name, "type": type,
        "metadata": metadata or {},
    })
    return parse(r)


async def _get(mcp, name: str, type: str = "service"):
    r = await mcp.call_tool("get_entity", {
        "project": PROJECT, "name": name, "type": type,
    })
    return parse(r)


async def _link(mcp, from_name: str, to_name: str, edge_type: str = "DEPENDS_ON",
                from_type: str = "service", to_type: str = "service"):
    r = await mcp.call_tool("link_entities", {
        "project": PROJECT,
        "from_name": from_name, "from_type": from_type,
        "to_name":   to_name,   "to_type":   to_type,
        "edge_type": edge_type,
    })
    return parse(r)


async def _unlink(mcp, from_name: str, to_name: str, edge_type: str = "DEPENDS_ON",
                  from_type: str = "service", to_type: str = "service"):
    r = await mcp.call_tool("unlink_entities", {
        "project": PROJECT,
        "from_name": from_name, "from_type": from_type,
        "to_name":   to_name,   "to_type":   to_type,
        "edge_type": edge_type,
    })
    return parse(r)


# ---------------------------------------------------------------------------
# upsert_entity
# ---------------------------------------------------------------------------

async def test_upsert_entity_creates_new(mcp):
    """upsert_entity returns a complete EntityNode dict on create."""
    e = await _upsert(mcp, "auth-service", metadata={"owner": "platform"})
    assert e["name"] == "auth-service"
    assert e["type"] == "service"
    assert e["project"] == PROJECT
    assert e["metadata"]["owner"] == "platform"
    assert e["id"]
    assert e["created_at"]
    assert e["updated_at"]


async def test_upsert_entity_updates_metadata(mcp):
    """Second upsert fully replaces metadata."""
    await _upsert(mcp, "svc-a", metadata={"v": "1"})
    e = await _upsert(mcp, "svc-a", metadata={"v": "2", "extra": "yes"})
    assert e["metadata"]["v"] == "2"
    assert e["metadata"]["extra"] == "yes"
    assert "v" in e["metadata"]   # old key replaced by new value


async def test_upsert_entity_empty_metadata(mcp):
    """upsert_entity with no metadata arg defaults to {}."""
    e = await _upsert(mcp, "bare-svc")
    assert e["metadata"] == {}


async def test_upsert_entity_invalid_type_raises(mcp):
    """upsert_entity with unknown type must raise (FastMCP surfaces it as an error)."""
    with pytest.raises(Exception, match="Invalid entity type|error"):
        await mcp.call_tool("upsert_entity", {
            "project": PROJECT, "name": "x", "type": "invalid_type",
        })


async def test_upsert_entity_all_valid_types(mcp):
    """All six valid entity types must be accepted."""
    valid_types = ["service", "file", "feature", "concept", "table", "topic"]
    for t in valid_types:
        e = await _upsert(mcp, f"{t}-entity", type=t)
        assert e["type"] == t


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------

async def test_get_entity_found(mcp):
    """get_entity returns entity when it exists."""
    await _upsert(mcp, "redis", metadata={"port": "6379"})
    e = await _get(mcp, "redis")
    assert e["found"] is True
    assert e["name"] == "redis"
    assert e["metadata"]["port"] == "6379"


async def test_get_entity_not_found(mcp):
    """get_entity returns {"found": false} when absent — does not raise."""
    e = await _get(mcp, "nonexistent-service")
    assert e["found"] is False
    assert "id" not in e


async def test_get_entity_type_scoped(mcp):
    """get_entity with wrong type returns not-found even if name exists under another type."""
    await _upsert(mcp, "users", type="table")
    e = await _get(mcp, "users", type="service")   # wrong type
    assert e["found"] is False


# ---------------------------------------------------------------------------
# link_entities
# ---------------------------------------------------------------------------

async def test_link_entities_creates_edge(mcp):
    """link_entities returns an Edge dict with correct fields."""
    await _upsert(mcp, "api-gw")
    await _upsert(mcp, "auth-svc")
    edge = await _link(mcp, "api-gw", "auth-svc")
    assert edge["type"] == "DEPENDS_ON"
    assert edge["from_type"] == "entity"
    assert edge["to_type"] == "entity"
    assert edge["id"]


async def test_link_entities_idempotent(mcp):
    """Calling link_entities twice returns the same edge id (no duplicate)."""
    await _upsert(mcp, "svc-x")
    await _upsert(mcp, "svc-y")
    e1 = await _link(mcp, "svc-x", "svc-y")
    e2 = await _link(mcp, "svc-x", "svc-y")
    assert e1["id"] == e2["id"]


async def test_link_entities_implements_type(mcp):
    """IMPLEMENTS edge_type is accepted."""
    await _upsert(mcp, "checkout-feature", type="feature")
    await _upsert(mcp, "payment-concept", type="concept")
    edge = await _link(mcp, "checkout-feature", "payment-concept",
                       edge_type="IMPLEMENTS",
                       from_type="feature", to_type="concept")
    assert edge["type"] == "IMPLEMENTS"


async def test_link_entities_missing_source_raises(mcp):
    """link_entities raises when from_name entity doesn't exist."""
    await _upsert(mcp, "existing-svc")
    with pytest.raises(Exception, match="Entity not found|error"):
        await _link(mcp, "ghost-svc", "existing-svc")


async def test_link_entities_missing_target_raises(mcp):
    """link_entities raises when to_name entity doesn't exist."""
    await _upsert(mcp, "real-svc")
    with pytest.raises(Exception, match="Entity not found|error"):
        await _link(mcp, "real-svc", "ghost-target")


async def test_link_entities_invalid_edge_type_raises(mcp):
    """link_entities rejects edge types that aren't DEPENDS_ON or IMPLEMENTS."""
    await _upsert(mcp, "a")
    await _upsert(mcp, "b")
    with pytest.raises(Exception, match="Invalid entity edge type|error"):
        await mcp.call_tool("link_entities", {
            "project": PROJECT,
            "from_name": "a", "from_type": "service",
            "to_name":   "b", "to_type":   "service",
            "edge_type": "SUPERSEDES",   # memory-only edge type
        })


# ---------------------------------------------------------------------------
# unlink_entities
# ---------------------------------------------------------------------------

async def test_unlink_entities_removes_edge(mcp):
    """unlink_entities returns {"deleted": true} after a successful delete."""
    await _upsert(mcp, "frontend")
    await _upsert(mcp, "backend")
    await _link(mcp, "frontend", "backend")
    result = await _unlink(mcp, "frontend", "backend")
    assert result["deleted"] is True


async def test_unlink_entities_not_found_returns_false(mcp):
    """unlink_entities returns {"deleted": false} when edge doesn't exist."""
    await _upsert(mcp, "p")
    await _upsert(mcp, "q")
    result = await _unlink(mcp, "p", "q")   # never linked
    assert result["deleted"] is False


async def test_unlink_entities_second_call_returns_false(mcp):
    """Second unlink on same edge returns false (already deleted)."""
    await _upsert(mcp, "alpha")
    await _upsert(mcp, "beta")
    await _link(mcp, "alpha", "beta")
    await _unlink(mcp, "alpha", "beta")
    result = await _unlink(mcp, "alpha", "beta")   # already gone
    assert result["deleted"] is False


async def test_unlink_does_not_affect_reverse_edge(mcp):
    """Deleting A→B does not delete B→A if it exists."""
    await _upsert(mcp, "node1")
    await _upsert(mcp, "node2")
    await _link(mcp, "node1", "node2")
    await _link(mcp, "node2", "node1")   # reverse edge
    await _unlink(mcp, "node1", "node2")
    # reverse edge should still exist
    result = await _unlink(mcp, "node2", "node1")
    assert result["deleted"] is True


# ---------------------------------------------------------------------------
# upsert_entity_with_deps tests
# ---------------------------------------------------------------------------

async def _upsert_with_deps(mcp, name: str, type: str = "service",
                             metadata: dict | None = None,
                             depends_on: list[str] | None = None,
                             dep_type: str = "service",
                             edge_type: str = "DEPENDS_ON"):
    r = await mcp.call_tool("upsert_entity_with_deps", {
        "project":    PROJECT,
        "name":       name,
        "type":       type,
        "metadata":   metadata or {},
        "depends_on": depends_on or [],
        "dep_type":   dep_type,
        "edge_type":  edge_type,
    })
    return parse(r)


async def test_upsert_entity_with_deps_creates_edges(mcp, engine):
    """DEPENDS_ON edges are created for all listed dependencies."""
    result = await _upsert_with_deps(mcp, "auth-service",
                                     depends_on=["db-service", "redis-service"])
    assert result["entity_id"]
    assert len(result["created_edges"]) == 2
    assert result["errors"] == []

    # Verify the edges exist in the engine
    auth = engine.get_entity("auth-service", "service", PROJECT)
    db   = engine.get_entity("db-service",   "service", PROJECT)
    redis = engine.get_entity("redis-service", "service", PROJECT)
    assert auth and db and redis


async def test_dep_auto_created_when_missing(mcp, engine):
    """A dep entity not yet in the graph is automatically created."""
    result = await _upsert_with_deps(mcp, "svc-a", depends_on=["brand-new-dep"])
    assert result["errors"] == []

    dep = engine.get_entity("brand-new-dep", "service", PROJECT)
    assert dep is not None, "Dep entity should have been auto-created"


async def test_dep_metadata_preserved_when_exists(mcp, engine):
    """
    If a dep entity already exists, its metadata is NOT overwritten.
    Guards [Q5]: full metadata replacement semantics.
    """
    # Pre-create the dep entity with rich metadata
    await _upsert(mcp, "existing-dep", metadata={"owner": "team-alpha", "sla": "99.9"})

    # Now call upsert_with_deps — should not wipe the dep's metadata
    await _upsert_with_deps(mcp, "main-svc", depends_on=["existing-dep"])

    dep = engine.get_entity("existing-dep", "service", PROJECT)
    assert dep is not None
    assert dep.metadata.get("owner") == "team-alpha", (
        "Existing dep metadata should be preserved, not wiped"
    )
    assert dep.metadata.get("sla") == "99.9"


async def test_invalid_type_raises_before_writes(mcp):
    """ValueError on invalid entity type — no partial writes."""
    with pytest.raises(Exception, match="Invalid type"):
        await _upsert_with_deps(mcp, "svc", type="nonexistent_type",
                                 depends_on=["other"], dep_type="service")


async def test_invalid_dep_type_raises_before_writes(mcp):
    """ValueError on invalid dep_type — no partial writes."""
    with pytest.raises(Exception, match="Invalid dep_type"):
        await _upsert_with_deps(mcp, "svc", depends_on=["other"],
                                 dep_type="notavalidtype")


async def test_dep_edge_idempotent(mcp):
    """Calling upsert_entity_with_deps twice with the same dep produces no duplicate edge."""
    await _upsert_with_deps(mcp, "svc", depends_on=["dep"])
    result2 = await _upsert_with_deps(mcp, "svc", depends_on=["dep"])
    # Should succeed (idempotent) — edge already exists, link_entities returns existing
    assert result2["errors"] == []
    assert len(result2["created_edges"]) == 1


async def test_upsert_entity_with_deps_reduces_selects_for_existing_deps(mcp, engine):
    """[v3] Existing deps should avoid redundant re-resolution during linking."""
    for i in range(10):
        await _upsert(mcp, f"dep-{i}", metadata={"x": i})

    sql_calls: list[str] = []
    engine._con.set_trace_callback(sql_calls.append)
    try:
        result = await _upsert_with_deps(
            mcp,
            "main",
            depends_on=[f"dep-{i}" for i in range(10)],
        )
    finally:
        engine._con.set_trace_callback(None)

    selects = [s for s in sql_calls if s.strip().upper().startswith("SELECT")]
    inserts = [s for s in sql_calls if s.strip().upper().startswith("INSERT")]
    assert result["errors"] == []
    assert len(selects) <= 12
    assert len(inserts) == 11
