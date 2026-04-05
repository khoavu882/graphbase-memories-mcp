"""
Analysis tool tests: get_blast_radius, get_stale_memories, purge_expired_memories.
Covers [R1] typed return structure, [Q4] flag-only decay.
"""
from __future__ import annotations

from conftest import PROJECT, parse


async def _store(mcp, **kwargs):
    defaults = {"project": PROJECT, "entities": [], "tags": []}
    r = await mcp.call_tool("store_memory", {**defaults, **kwargs})
    return parse(r)


# ---------------------------------------------------------------------------
# get_blast_radius
# ---------------------------------------------------------------------------

async def test_blast_radius_r1_typed_structure(mcp):
    """[R1] get_blast_radius must return typed dict with all expected keys."""
    await _store(mcp, title="Auth impl", content="JWT in auth-service.", type="decision",
                 entities=["auth-service", "redis"])
    r = await mcp.call_tool("get_blast_radius", {"entity_name": "auth-service", "project": PROJECT})
    br = parse(r)
    assert "entity_name" in br
    assert "project" in br
    assert "depth" in br
    assert "total_references" in br
    assert "memories" in br
    assert "related_entities" in br


async def test_blast_radius_counts_direct_references(mcp):
    await _store(mcp, title="M1", content="auth-service JWT.", type="decision",
                 entities=["auth-service"])
    await _store(mcp, title="M2", content="auth-service Redis.", type="pattern",
                 entities=["auth-service", "redis"])
    r = await mcp.call_tool("get_blast_radius", {"entity_name": "auth-service", "project": PROJECT})
    br = parse(r)
    assert br["total_references"] == 2
    assert len(br["memories"]) == 2


async def test_blast_radius_includes_related_entities(mcp):
    await _store(mcp, title="M1", content="auth+redis.", type="decision",
                 entities=["auth-service", "redis"])
    r = await mcp.call_tool("get_blast_radius", {"entity_name": "auth-service", "project": PROJECT})
    br = parse(r)
    names = {e["name"] for e in br["related_entities"]}
    assert "redis" in names


async def test_blast_radius_unknown_entity_empty(mcp):
    r = await mcp.call_tool("get_blast_radius", {"entity_name": "does-not-exist", "project": PROJECT})
    br = parse(r)
    assert br["total_references"] == 0
    assert br["memories"] == []
    assert br["related_entities"] == []


# ---------------------------------------------------------------------------
# get_stale_memories + purge_expired_memories  (Q4 flag-only decay)
# ---------------------------------------------------------------------------

async def test_stale_memories_flags_expired(mcp, engine):
    """[Q4] get_stale_memories must flag stale memories as is_expired=1."""
    m = await _store(mcp, title="Old decision", content="Stale.", type="decision")
    engine._backdate(m["id"], 35)

    r = await mcp.call_tool("get_stale_memories", {"project": PROJECT, "age_days": 30})
    stale = parse(r)
    assert len(stale) == 1
    assert stale[0]["id"] == m["id"]
    assert stale[0]["is_expired"] is True

    # Verify flag is persisted in DB
    node = engine.get_memory(m["id"])
    assert node.is_expired is True


async def test_stale_memories_fresh_not_flagged(mcp, engine):
    """Fresh memories (within age_days) must not be flagged."""
    m = await _store(mcp, title="Fresh", content="Recent.", type="pattern")
    engine._backdate(m["id"], 10)

    r = await mcp.call_tool("get_stale_memories", {"project": PROJECT, "age_days": 30})
    stale = parse(r)
    ids = [s["id"] for s in stale]
    assert m["id"] not in ids


async def test_purge_expired_permanently_deletes(mcp, engine):
    """[Q4] purge_expired_memories must permanently delete is_expired=1 memories."""
    m = await _store(mcp, title="Expired old", content="Old.", type="decision")
    engine._backdate(m["id"], 100)
    # Flag it expired (get_stale_memories flags is_expired=1 but also resets updated_at)
    await mcp.call_tool("get_stale_memories", {"project": PROJECT, "age_days": 30})
    # Re-backdate after flagging so updated_at is still old enough for purge
    engine._backdate(m["id"], 100)

    r = await mcp.call_tool("purge_expired_memories", {"project": PROJECT, "older_than_days": 90})
    result = parse(r)
    assert result["purged_count"] == 1

    # Memory must be gone even with include_deleted=True
    assert engine.get_memory(m["id"], include_deleted=True) is None


async def test_purge_fresh_memories_untouched(mcp, engine):
    """[Q4] purge_expired must not touch fresh (non-expired) memories."""
    m = await _store(mcp, title="Fresh", content="Current.", type="pattern")

    r = await mcp.call_tool("purge_expired_memories", {"project": PROJECT, "older_than_days": 90})
    result = parse(r)
    assert result["purged_count"] == 0
    assert engine.get_memory(m["id"]) is not None


async def test_purge_returns_correct_metadata(mcp, engine):
    """purge result must include project and older_than_days."""
    r = await mcp.call_tool("purge_expired_memories", {
        "project": PROJECT, "older_than_days": 60
    })
    result = parse(r)
    assert result["project"] == PROJECT
    assert result["older_than_days"] == 60
