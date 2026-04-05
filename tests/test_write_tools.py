"""
Write tool tests: store_memory, relate_memories.
Covers direction validation for LEARNED_DURING edges.
"""
from __future__ import annotations

import pytest
from conftest import PROJECT, parse


async def test_store_memory_returns_id(mcp):
    r = await mcp.call_tool("store_memory", {
        "project": PROJECT,
        "title": "Auth design decision",
        "content": "Use JWT with 1h expiry.",
        "type": "decision",
        "entities": ["auth-service"],
        "tags": ["auth"],
    })
    m = parse(r)
    assert "id" in m
    assert m["title"] == "Auth design decision"
    assert m["type"] == "decision"
    assert m["id"]  # project not included in store_memory return


async def test_store_memory_invalid_type_raises(mcp):
    with pytest.raises(Exception):
        await mcp.call_tool("store_memory", {
            "project": PROJECT,
            "title": "Bad type",
            "content": "content",
            "type": "invalid_type",
            "entities": [],
            "tags": [],
        })


async def test_store_memory_with_entities_linkable(mcp, engine):
    r = await mcp.call_tool("store_memory", {
        "project": PROJECT,
        "title": "Redis caching",
        "content": "Adopted Redis for session storage.",
        "type": "pattern",
        "entities": ["redis", "auth-service"],
        "tags": [],
    })
    m = parse(r)
    entities = engine.get_entities_for_memory(m["id"])
    names = {e.name for e in entities}
    assert "redis" in names
    assert "auth-service" in names


async def test_relate_memories_supersedes(mcp):
    r1 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Old pattern", "content": "Old.",
        "type": "pattern", "entities": [], "tags": [],
    })
    r2 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "New pattern", "content": "New.",
        "type": "pattern", "entities": [], "tags": [],
    })
    m_old = parse(r1)
    m_new = parse(r2)

    r = await mcp.call_tool("relate_memories", {
        "project": PROJECT,
        "from_id": m_new["id"],
        "to_id": m_old["id"],
        "relationship": "SUPERSEDES",
    })
    edge = parse(r)
    assert edge["type"] == "SUPERSEDES"
    assert edge["from_id"] == m_new["id"]


async def test_relate_memories_learned_during_valid(mcp):
    """LEARNED_DURING: decision → session is valid."""
    r_session = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Sprint session",
        "content": "Sprint planning.", "type": "session", "entities": [], "tags": [],
    })
    r_decision = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Design decision",
        "content": "Chose JWT.", "type": "decision", "entities": [], "tags": [],
    })
    session = parse(r_session)
    decision = parse(r_decision)

    r = await mcp.call_tool("relate_memories", {
        "project": PROJECT,
        "from_id": decision["id"],
        "to_id": session["id"],
        "relationship": "LEARNED_DURING",
    })
    edge = parse(r)
    assert edge["type"] == "LEARNED_DURING"


async def test_relate_memories_learned_during_invalid_direction(mcp):
    """LEARNED_DURING: session → session must be rejected (invalid direction)."""
    r1 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Session A",
        "content": "content.", "type": "session", "entities": [], "tags": [],
    })
    r2 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Session B",
        "content": "content.", "type": "session", "entities": [], "tags": [],
    })
    s1 = parse(r1)
    s2 = parse(r2)

    with pytest.raises(Exception, match="LEARNED_DURING"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": s1["id"],
            "to_id": s2["id"],
            "relationship": "LEARNED_DURING",
        })


async def test_relate_memories_unknown_relationship_raises(mcp):
    """Unknown relationship type must raise ValueError."""
    r1 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "M1", "content": "c.", "type": "decision",
        "entities": [], "tags": [],
    })
    r2 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "M2", "content": "c.", "type": "decision",
        "entities": [], "tags": [],
    })
    m1 = parse(r1)
    m2 = parse(r2)

    with pytest.raises(Exception, match="Unknown relationship"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": m1["id"],
            "to_id": m2["id"],
            "relationship": "INVENTED_EDGE",
        })


async def test_relate_memories_self_loop_raises(mcp):
    """from_id == to_id must be rejected."""
    r = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Lone memory", "content": "c.", "type": "context",
        "entities": [], "tags": [],
    })
    m = parse(r)

    with pytest.raises(Exception, match="different"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": m["id"],
            "to_id": m["id"],
            "relationship": "RELATES_TO",
        })


async def test_relate_memories_missing_from_id_raises(mcp):
    """Non-existent from_id must raise ValueError."""
    r = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Existing", "content": "c.", "type": "context",
        "entities": [], "tags": [],
    })
    m = parse(r)

    with pytest.raises(Exception, match="not found"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": "00000000-0000-0000-0000-000000000000",
            "to_id": m["id"],
            "relationship": "RELATES_TO",
        })


async def test_relate_memories_missing_to_id_raises(mcp):
    """Non-existent to_id must raise ValueError."""
    r = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Existing", "content": "c.", "type": "context",
        "entities": [], "tags": [],
    })
    m = parse(r)

    with pytest.raises(Exception, match="not found"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": m["id"],
            "to_id": "00000000-0000-0000-0000-000000000000",
            "relationship": "RELATES_TO",
        })


async def test_relate_memories_learned_during_invalid_to_type(mcp):
    """LEARNED_DURING: decision → decision is rejected (to_type must be session)."""
    r1 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Decision A", "content": "c.", "type": "decision",
        "entities": [], "tags": [],
    })
    r2 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Decision B", "content": "c.", "type": "decision",
        "entities": [], "tags": [],
    })
    d1 = parse(r1)
    d2 = parse(r2)

    with pytest.raises(Exception, match="LEARNED_DURING"):
        await mcp.call_tool("relate_memories", {
            "project": PROJECT,
            "from_id": d1["id"],
            "to_id": d2["id"],
            "relationship": "LEARNED_DURING",
        })
