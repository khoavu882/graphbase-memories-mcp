"""
Write tool tests: store_memory, relate_memories.
Covers direction validation for LEARNED_DURING edges.
"""
from __future__ import annotations

import pytest
from conftest import PROJECT, parse
from graphbase_memories.tools._session_batch import store_session_batch


class _ConnectionSpy:
    """Proxy that counts commits while delegating all other calls to sqlite3."""

    def __init__(self, con):
        self._con = con
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1
        return self._con.commit()

    def __getattr__(self, name):
        return getattr(self._con, name)


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


async def test_relate_memories_idempotent_returns_same_edge(mcp):
    """Repeated relate_memories calls must reuse the same relationship row."""
    r1 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Existing A", "content": "A.",
        "type": "pattern", "entities": [], "tags": [],
    })
    r2 = await mcp.call_tool("store_memory", {
        "project": PROJECT, "title": "Existing B", "content": "B.",
        "type": "pattern", "entities": [], "tags": [],
    })
    m1 = parse(r1)
    m2 = parse(r2)

    edge1 = parse(await mcp.call_tool("relate_memories", {
        "project": PROJECT,
        "from_id": m1["id"],
        "to_id": m2["id"],
        "relationship": "RELATES_TO",
    }))
    edge2 = parse(await mcp.call_tool("relate_memories", {
        "project": PROJECT,
        "from_id": m1["id"],
        "to_id": m2["id"],
        "relationship": "RELATES_TO",
    }))
    assert edge1["id"] == edge2["id"]


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


def test_store_session_batch_reduces_commits(engine):
    """[v3] Batch write mode collapses per-item writes to one commit each."""
    spy = _ConnectionSpy(engine._con)
    engine._con = spy

    session = {"title": "S", "content": "session", "tags": []}
    decisions = [{"title": f"D{i}", "content": "dec", "tags": []} for i in range(5)]
    patterns = [{"title": f"P{i}", "content": "pat", "tags": []} for i in range(3)]

    result = store_session_batch(engine, PROJECT, session, decisions, patterns)

    assert result["errors"] == []
    assert spy.commit_count == 9


def test_store_session_batch_rolls_back_failed_item(engine, monkeypatch):
    """[v3] A failure inside batch_write must roll back the current item."""
    original_store_edge = engine.store_edge
    seen_learned_during = 0

    def failing_store_edge(edge):
        nonlocal seen_learned_during
        if edge.type == "LEARNED_DURING":
            seen_learned_during += 1
            if seen_learned_during == 1:
                raise RuntimeError("simulated edge failure")
        return original_store_edge(edge)

    monkeypatch.setattr(engine, "store_edge", failing_store_edge)

    result = store_session_batch(
        engine,
        PROJECT,
        {"title": "Session", "content": "session", "tags": []},
        [{"title": "Decision 0", "content": "dec", "tags": []}],
        [],
    )

    assert len(result["errors"]) == 1
    assert result["errors"][0]["type"] == "decision"
    titles = {m.title for m in engine.list_memories(PROJECT, type="decision")}
    assert "Decision 0" not in titles


def test_store_session_batch_s2_isolation(engine, monkeypatch):
    """[S2] A later item failure must not roll back earlier committed items."""
    original_store_edge = engine.store_edge
    seen_learned_during = 0

    def failing_store_edge(edge):
        nonlocal seen_learned_during
        if edge.type == "LEARNED_DURING":
            seen_learned_during += 1
            if seen_learned_during == 3:
                raise RuntimeError("third item fails")
        return original_store_edge(edge)

    monkeypatch.setattr(engine, "store_edge", failing_store_edge)

    decisions = [{"title": f"D{i}", "content": "dec", "tags": []} for i in range(5)]
    result = store_session_batch(
        engine,
        PROJECT,
        {"title": "Session 2", "content": "session", "tags": []},
        decisions,
        [],
    )

    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 2
    titles = {m.title for m in engine.list_memories(PROJECT, type="decision")}
    assert {"D0", "D1", "D3", "D4"}.issubset(titles)
    assert "D2" not in titles
